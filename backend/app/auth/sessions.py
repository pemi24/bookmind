"""Server-side sessions in PostgreSQL, with an HttpOnly cookie and a CSRF token.

The browser gets two cookies: `bm_session` (random, HttpOnly: scripts can't read it) and
`bm_csrf` (random, readable by BookMind's own pages). Changing requests must send the CSRF
value back in the X-CSRF-Token header; another site can't read the cookie, so it can't forge
that header. Only SHA-256 hashes of both values are stored.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User, UserSession
from app.db.session import SessionLocal

SESSION_COOKIE = "bm_session"
CSRF_COOKIE = "bm_csrf"
CSRF_HEADER = "x-csrf-token"
TOUCH_EVERY = timedelta(minutes=5)  # how often a busy session's expiry is pushed back


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _lifetime(remember: bool) -> timedelta:
    s = get_settings()
    return timedelta(days=s.remember_days) if remember else timedelta(hours=s.session_hours)


def _secure(request: Request) -> bool:
    setting = get_settings().cookie_secure.lower()
    if setting in ("true", "1", "yes"):
        return True
    if setting in ("false", "0", "no"):
        return False
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


async def create_session(db: AsyncSession, user: User, remember: bool, request: Request,
                         response: Response) -> None:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + _lifetime(remember)
    db.add(UserSession(user_id=user.id, token_hash=digest(token), csrf_hash=digest(csrf), remember=remember,
                       user_agent=(request.headers.get("user-agent") or "")[:300], ip=client_ip(request),
                       expires_at=expires))
    await db.commit()
    max_age = int(_lifetime(remember).total_seconds()) if remember else None  # browser-session cookie otherwise
    common = {"path": "/", "samesite": "lax", "secure": _secure(request), "max_age": max_age}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def load(db: AsyncSession, request: Request) -> tuple[UserSession, User] | None:
    """The signed-in session and user for this request, or None. Extends the session while it's used."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = (await db.execute(
        select(UserSession, User).join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == digest(token)))).first()
    if row is None:
        return None
    sess, user = row
    now = datetime.now(timezone.utc)
    if sess.expires_at <= now or not user.is_active:
        return None
    if now - sess.last_seen_at > TOUCH_EVERY:
        # Separate transaction: never commits the endpoint's own pending work.
        async with SessionLocal() as tdb:
            await tdb.execute(update(UserSession).where(UserSession.id == sess.id)
                              .values(last_seen_at=now, expires_at=now + _lifetime(sess.remember)))
            await tdb.commit()
    return sess, user


def csrf_ok(sess: UserSession, request: Request) -> bool:
    sent = request.headers.get(CSRF_HEADER) or ""
    return bool(sent) and same(digest(sent), sess.csrf_hash)


async def revoke(db: AsyncSession, session_id: int) -> None:
    await db.execute(delete(UserSession).where(UserSession.id == session_id))
    await db.commit()


async def revoke_all(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    await db.commit()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
