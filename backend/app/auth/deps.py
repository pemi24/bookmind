"""Who is making this request. Every endpoint that touches a user's data depends on `current_user`."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import sessions
from app.db.models import User, UserSession
from app.db.session import get_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
APP_HEADER = "x-requested-with"  # anonymous changing requests (sign in, sign up...) must send "BookMind"


async def current_session(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[UserSession, User]:
    found = await sessions.load(db, request)
    if found is None:
        raise HTTPException(401, "Please sign in.")
    sess, user = found
    if request.method not in SAFE_METHODS and not sessions.csrf_ok(sess, request):
        raise HTTPException(403, "Your session token is missing or out of date. Reload the page and try again.")
    request.state.user_id = user.id
    return sess, user


async def current_user(found: tuple[UserSession, User] = Depends(current_session)) -> User:
    return found[1]


async def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(404, "Not found.")
    return user


def app_request(request: Request) -> None:
    """Anonymous changing requests must come from BookMind's own pages: a custom header can't be sent
    cross-site without the browser asking permission first (which BookMind never grants)."""
    if request.headers.get(APP_HEADER, "").lower() != "bookmind":
        raise HTTPException(403, "This request must come from the BookMind app.")


CurrentUser = Annotated[User, Depends(current_user)]
