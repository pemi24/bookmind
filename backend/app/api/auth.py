"""Sign up, sign in / out, password reset, email verification."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mailer, ratelimit, sessions
from app.auth.deps import app_request, current_session
from app.auth.passwords import hash_password, needs_rehash, password_problem, verify_password
from app.config import get_settings
from app.db.models import AuthToken, User
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVALID = "Invalid email or password."
LOCKED = "Too many failed sign-in attempts. Try again in a few minutes."
FIFTEEN_MIN, HOUR = 15 * 60, 60 * 60


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "is_admin": u.is_admin,
            "email_verified": u.email_verified_at is not None, "settings": u.settings or {},
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _norm(email: str) -> str:
    return email.strip().lower()


def _base_url(request: Request) -> str:
    """Where links in emails should point: the page the user is on (dev: Vite's port), unless configured."""
    configured = get_settings().app_base_url.strip().rstrip("/")
    if configured:
        return configured
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return origin.rstrip("/")
    return str(request.base_url).rstrip("/")


async def _issue_token(db: AsyncSession, user: User, kind: str, lifetime: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, kind=kind, token_hash=sessions.digest(token),
                     expires_at=datetime.now(timezone.utc) + lifetime))
    await db.commit()
    return token


async def _use_token(db: AsyncSession, token: str, kind: str) -> AuthToken:
    row = await db.scalar(select(AuthToken).where(AuthToken.token_hash == sessions.digest(token),
                                                  AuthToken.kind == kind))
    if row is None or row.used_at is not None or row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(400, "This link is invalid or has expired. Request a new one.")
    row.used_at = datetime.now(timezone.utc)
    return row


async def _send_verification(db: AsyncSession, user: User, request: Request) -> None:
    token = await _issue_token(db, user, "verify", timedelta(hours=get_settings().verify_token_hours))
    await mailer.send_email(user.email, "Confirm your BookMind email",
                            f"Hello {user.display_name},\n\nConfirm your email address for BookMind:\n"
                            f"{_base_url(request)}/#/verify?token={token}\n\n"
                            f"This link expires in {get_settings().verify_token_hours} hours.")


# ---------------------------------------------------------------- sign up / in / out

class SignupRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    display_name: str = Field(default="", max_length=100)


@router.get("/config")
async def auth_config():
    s = get_settings()
    return {"password_min_length": s.password_min_length, "require_email_verification": s.require_email_verification}


@router.post("/signup", status_code=201, dependencies=[Depends(app_request)])
async def signup(req: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    ratelimit.check(f"signup:ip:{sessions.client_ip(request)}", s.signup_rate_limit, HOUR, "sign-up attempts")
    email = _norm(req.email)
    if not EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if problem := password_problem(req.password, email):
        raise HTTPException(422, problem)
    if await db.scalar(select(User.id).where(User.email == email)):
        # Saying so is unavoidable at sign-up (the address can't be used twice); sign-in stays generic.
        raise HTTPException(409, "An account with this email already exists. Sign in, or reset your password.")
    name = " ".join(req.display_name.split()) or email.split("@")[0]
    user = User(email=email, display_name=name[:100], password_hash=hash_password(req.password), settings={},
                email_verified_at=None if s.require_email_verification else datetime.now(timezone.utc))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    if s.require_email_verification:
        await _send_verification(db, user, request)
        return {"user": user_dict(user), "verification_required": True}
    await sessions.create_session(db, user, False, request, response)
    return {"user": user_dict(user), "verification_required": False}


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    remember: bool = False


@router.post("/login", dependencies=[Depends(app_request)])
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    email = _norm(req.email)
    ratelimit.check(f"login:ip:{sessions.client_ip(request)}", s.login_rate_limit, FIFTEEN_MIN, "sign-in attempts")
    # Repeated failures for one address are slowed down whether or not the account exists.
    if ratelimit.count(f"login:fail:{email}", FIFTEEN_MIN) >= s.lockout_after_failures:
        raise HTTPException(429, LOCKED)
    user = await db.scalar(select(User).where(User.email == email))
    now = datetime.now(timezone.utc)
    if user is not None and user.locked_until and user.locked_until > now:
        raise HTTPException(429, LOCKED)
    if user is None or not user.is_active or not verify_password(user.password_hash, req.password):
        ratelimit.check(f"login:fail:{email}", 10_000, FIFTEEN_MIN)  # just counts
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= s.lockout_after_failures:
                extra = user.failed_logins - s.lockout_after_failures
                user.locked_until = now + timedelta(seconds=min(60 * 2 ** extra, 15 * 60))
            await db.commit()
        raise HTTPException(401, INVALID)
    if s.require_email_verification and user.email_verified_at is None:
        raise HTTPException(403, "Confirm your email address first: check your inbox for the link.")
    user.failed_logins, user.locked_until = 0, None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
    ratelimit.reset(f"login:fail:{email}")
    await sessions.create_session(db, user, req.remember, request, response)
    return {"user": user_dict(user)}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Signs this browser out (works even if the session already expired)."""
    found = await sessions.load(db, request)
    if found:
        sess, _ = found
        if not sessions.csrf_ok(sess, request):
            raise HTTPException(403, "Reload the page and try again.")
        await sessions.revoke(db, sess.id)
    sessions.clear_cookies(response)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(response: Response, found=Depends(current_session), db: AsyncSession = Depends(get_db)):
    """Signs out every browser and device, this one included."""
    await sessions.revoke_all(db, found[1].id)
    sessions.clear_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(found=Depends(current_session)):
    return {"user": user_dict(found[1])}


# ---------------------------------------------------------------- password reset

class ForgotRequest(BaseModel):
    email: str = Field(max_length=320)


@router.post("/forgot", status_code=202, dependencies=[Depends(app_request)])
async def forgot_password(req: ForgotRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Always the same answer, so it doesn't reveal who has an account."""
    s = get_settings()
    email = _norm(req.email)
    ratelimit.check(f"reset:ip:{sessions.client_ip(request)}", s.reset_rate_limit, HOUR, "reset requests")
    ratelimit.check(f"reset:email:{email}", s.reset_rate_limit, HOUR, "reset requests")
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active:
        token = await _issue_token(db, user, "reset", timedelta(minutes=s.reset_token_minutes))
        await mailer.send_email(user.email, "Reset your BookMind password",
                                f"Hello {user.display_name},\n\nSomeone (hopefully you) asked to reset your "
                                f"BookMind password. Choose a new one here:\n{_base_url(request)}/#/reset?token={token}"
                                f"\n\nThis link works once and expires in {s.reset_token_minutes} minutes. "
                                "If you didn't ask for this, ignore this email.")
    return {"ok": True, "message": "If an account exists for that email, a reset link is on its way."}


class ResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)


@router.post("/reset", dependencies=[Depends(app_request)])
async def reset_password(req: ResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ratelimit.check(f"reset:ip:{sessions.client_ip(request)}", get_settings().reset_rate_limit * 4, HOUR,
                    "reset attempts")
    row = await _use_token(db, req.token, "reset")
    user = await db.get(User, row.user_id)
    if problem := password_problem(req.password, user.email):
        await db.rollback()  # the token stays usable for a better password
        raise HTTPException(422, problem)
    user.password_hash = hash_password(req.password)
    user.failed_logins, user.locked_until = 0, None
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)  # the link proved they own the address
    # Older reset links stop working too, and every device is signed out.
    await db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == "reset",
                                             AuthToken.used_at.is_(None)).values(used_at=datetime.now(timezone.utc)))
    await db.commit()
    await sessions.revoke_all(db, user.id)
    ratelimit.reset(f"login:fail:{user.email}")
    return {"ok": True}


# ---------------------------------------------------------------- email verification

class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/verify", dependencies=[Depends(app_request)])
async def verify_email(req: VerifyRequest, db: AsyncSession = Depends(get_db)):
    row = await _use_token(db, req.token, "verify")
    user = await db.get(User, row.user_id)
    user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/resend-verification", status_code=202, dependencies=[Depends(app_request)])
async def resend_verification(req: ForgotRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = _norm(req.email)
    ratelimit.check(f"verify:email:{email}", 3, HOUR, "requests")
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and user.email_verified_at is None:
        await _send_verification(db, user, request)
    return {"ok": True}
