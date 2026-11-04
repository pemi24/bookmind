"""Admin: see accounts and their usage, suspend or promote them. Never anyone's book content."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.account import delete_user_and_files
from app.auth.deps import admin_user
from app.db.models import Book, Conversation, User, UserSession
from app.db.session import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


async def _get(db: AsyncSession, user_id: int, me: User) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Not found.")
    if u.id == me.id:
        raise HTTPException(400, "Change your own account from Settings.")
    return u


@router.get("/users")
async def list_users(me: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    books = (select(Book.user_id, func.count(Book.id).label("n"), func.coalesce(func.sum(Book.file_size), 0).label("size"))
             .group_by(Book.user_id).subquery())
    chats = select(Conversation.user_id, func.count(Conversation.id).label("n")).group_by(Conversation.user_id).subquery()
    seen = select(UserSession.user_id, func.max(UserSession.last_seen_at).label("at")).group_by(UserSession.user_id).subquery()
    rows = (await db.execute(
        select(User, books.c.n, books.c.size, chats.c.n, seen.c.at)
        .outerjoin(books, books.c.user_id == User.id).outerjoin(chats, chats.c.user_id == User.id)
        .outerjoin(seen, seen.c.user_id == User.id).order_by(User.id))).all()
    return [{
        "id": u.id, "email": u.email, "display_name": u.display_name, "is_admin": u.is_admin,
        "is_active": u.is_active, "email_verified": u.email_verified_at is not None, "has_password": bool(u.password_hash),
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_seen_at": at.isoformat() if at else None, "books": n_books or 0, "storage_bytes": int(size or 0),
        "chats": n_chats or 0, "is_me": u.id == me.id,
    } for u, n_books, size, n_chats, at in rows]


class UserUpdate(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


@router.patch("/users/{user_id}")
async def update_user(user_id: int, req: UserUpdate, me: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    u = await _get(db, user_id, me)
    if req.is_active is not None:
        u.is_active = req.is_active
        if not req.is_active:  # suspended: signed out everywhere at once
            await db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    if req.is_admin is not None:
        u.is_admin = req.is_admin
    await db.commit()
    return {"id": u.id, "is_active": u.is_active, "is_admin": u.is_admin}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, me: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    u = await _get(db, user_id, me)
    await delete_user_and_files(db, u)
