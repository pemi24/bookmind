"""Accounts: sign up / in / out, sessions, CSRF, rate limits, lockout, password reset, verification."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")
APP = {"X-Requested-With": "BookMind"}
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _fresh_limits():
    from app.auth import ratelimit

    ratelimit.clear_all()
    yield
    ratelimit.clear_all()


def client():
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60)


def new_email() -> str:
    return f"reader-{uuid.uuid4().hex[:10]}@example.com"


def csrf(c: httpx.AsyncClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("bm_csrf", "")}


async def signup(c, email=None, password=PASSWORD, name="Ada"):
    email = email or new_email()
    r = await c.post("/api/auth/signup", json={"email": email, "password": password, "display_name": name}, headers=APP)
    return email, r


async def test_signup_login_logout(test_db):
    async with client() as c:
        email, r = await signup(c)
        assert r.status_code == 201 and r.json()["user"]["email"] == email
        assert "password" not in r.text and "hash" not in r.text  # never returned
        cookie = r.headers.get_list("set-cookie")
        assert any("bm_session=" in h and "HttpOnly" in h and "SameSite=lax" in h for h in cookie)
        me = (await c.get("/api/auth/me")).json()["user"]
        assert me["display_name"] == "Ada" and me["is_admin"] is False

        assert (await c.post("/api/auth/logout")).status_code == 403  # no CSRF header
        assert (await c.post("/api/auth/logout", headers=csrf(c))).status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 401

        bad = await c.post("/api/auth/login", json={"email": email, "password": "wrong password!!"}, headers=APP)
        ghost = await c.post("/api/auth/login", json={"email": new_email(), "password": "wrong password!!"}, headers=APP)
        assert bad.status_code == ghost.status_code == 401
        assert bad.json()["detail"] == ghost.json()["detail"] == "Invalid email or password."  # no enumeration

        ok = await c.post("/api/auth/login", json={"email": email.upper(), "password": PASSWORD}, headers=APP)
        assert ok.status_code == 200 and (await c.get("/api/auth/me")).status_code == 200


async def test_signup_rules(test_db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "signup_rate_limit", 50)  # this test makes more attempts than the limit
    async with client() as c:
        assert (await signup(c, password="short"))[1].status_code == 422
        assert (await signup(c, password="aaaaaaaaaaaa"))[1].status_code == 422
        assert (await signup(c, password="password123"))[1].status_code == 422
        assert (await signup(c, email="not-an-email"))[1].status_code == 422
        email, _ = await signup(c)
        assert (await signup(c, email=email))[1].status_code == 409
        no_header = await c.post("/api/auth/signup", json={"email": new_email(), "password": PASSWORD})
        assert no_header.status_code == 403  # must come from the app (CSRF for anonymous requests)


async def test_lockout_after_repeated_failures(test_db):
    async with client() as c:
        email, _ = await signup(c)
        await c.post("/api/auth/logout", headers=csrf(c))
        for _ in range(5):
            r = await c.post("/api/auth/login", json={"email": email, "password": "nope nope nope"}, headers=APP)
            assert r.status_code == 401
        locked = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=APP)
        assert locked.status_code == 429  # even the right password waits now
        # Unknown addresses are slowed down the same way (no hint about who has an account).
        ghost = new_email()
        for _ in range(5):
            await c.post("/api/auth/login", json={"email": ghost, "password": "nope nope nope"}, headers=APP)
        assert (await c.post("/api/auth/login", json={"email": ghost, "password": "x" * 12}, headers=APP)).status_code == 429


async def test_rate_limit_per_ip(test_db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "signup_rate_limit", 2)
    async with client() as c:
        assert (await signup(c))[1].status_code == 201
        assert (await signup(c))[1].status_code == 201
        r = (await signup(c))[1]
        assert r.status_code == 429 and "Try again in" in r.json()["detail"]


async def test_logout_everywhere(test_db):
    async with client() as a, client() as b:
        email, _ = await signup(a)
        await b.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=APP)
        assert (await b.get("/api/auth/me")).status_code == 200
        assert (await a.post("/api/auth/logout-all", headers=csrf(a))).status_code == 200
        assert (await a.get("/api/auth/me")).status_code == 401 and (await b.get("/api/auth/me")).status_code == 401


async def test_password_reset_flow(test_db):
    from app.auth import mailer
    from app.db.models import AuthToken
    from app.db.session import SessionLocal

    async with client() as c:
        email, _ = await signup(c)
        r = await c.post("/api/auth/forgot", json={"email": email}, headers=APP)
        ghost = await c.post("/api/auth/forgot", json={"email": new_email()}, headers=APP)
        assert r.status_code == ghost.status_code == 202 and r.json() == ghost.json()  # same answer either way
        mail = next(m for m in reversed(mailer.sent) if m["to"] == email)
        token = re.search(r"#/reset\?token=([\w-]+)", mail["body"]).group(1)

        assert (await c.post("/api/auth/reset", json={"token": token, "password": "short"}, headers=APP)).status_code == 422
        ok = await c.post("/api/auth/reset", json={"token": token, "password": "a brand new passphrase"}, headers=APP)
        assert ok.status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 401  # every session signed out
        reused = await c.post("/api/auth/reset", json={"token": token, "password": "another new passphrase"}, headers=APP)
        assert reused.status_code == 400  # single use
        assert (await c.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=APP)).status_code == 401
        assert (await c.post("/api/auth/login", json={"email": email, "password": "a brand new passphrase"},
                             headers=APP)).status_code == 200

        # An expired link doesn't work.
        await c.post("/api/auth/forgot", json={"email": email}, headers=APP)
        token2 = re.search(r"#/reset\?token=([\w-]+)", next(m for m in reversed(mailer.sent) if m["to"] == email)["body"]).group(1)
        from sqlalchemy import update

        from app.auth.sessions import digest

        async with SessionLocal() as db:
            await db.execute(update(AuthToken).where(AuthToken.token_hash == digest(token2))
                             .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
            await db.commit()
        expired = await c.post("/api/auth/reset", json={"token": token2, "password": "yet another passphrase"}, headers=APP)
        assert expired.status_code == 400

        async with SessionLocal() as db:  # only hashes are stored
            from sqlalchemy import select

            stored = (await db.execute(select(AuthToken.token_hash))).scalars().all()
            assert token not in stored and digest(token) in stored


async def test_email_verification_when_required(test_db, monkeypatch):
    from app.auth import mailer
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "require_email_verification", True)
    async with client() as c:
        email, r = await signup(c)
        assert r.status_code == 201 and r.json()["verification_required"] is True
        assert (await c.get("/api/auth/me")).status_code == 401  # not signed in yet
        blocked = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=APP)
        assert blocked.status_code == 403
        token = re.search(r"#/verify\?token=([\w-]+)", next(m for m in reversed(mailer.sent) if m["to"] == email)["body"]).group(1)
        assert (await c.post("/api/auth/verify", json={"token": token}, headers=APP)).status_code == 200
        assert (await c.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=APP)).status_code == 200


async def test_existing_data_belongs_to_the_legacy_admin(test_db):
    from sqlalchemy import func, select

    from app.config import get_settings
    from app.db.models import Book, User
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        admin = await db.scalar(select(User).where(User.email == get_settings().admin_email.lower()))
        assert admin is not None and admin.is_admin
        orphans = await db.scalar(select(func.count()).select_from(Book).where(Book.user_id.is_(None)))
        assert orphans == 0
