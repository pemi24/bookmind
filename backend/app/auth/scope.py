"""Ownership checks: every lookup of a user's data goes through here.

Each helper finds the row only among the signed-in user's own data and raises 404 otherwise,
so someone else's book looks exactly like a book that doesn't exist (no 403 that would confirm
it's there). Rows without their own owner column are owned through their book.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, Chapter, Chunk, Conversation, Entity, Flashcard, Note, Quiz, User


def _uid(user: User | int) -> int:
    return user if isinstance(user, int) else user.id


async def book(db: AsyncSession, book_id: int, user: User | int) -> Book:
    row = await db.scalar(select(Book).where(Book.id == book_id, Book.user_id == _uid(user)))
    if row is None:
        raise HTTPException(404, "Book not found.")
    return row


async def book_ids(db: AsyncSession, user: User | int) -> list[int]:
    return list((await db.execute(select(Book.id).where(Book.user_id == _uid(user)))).scalars())


async def chapter(db: AsyncSession, chapter_id: int, user: User | int) -> Chapter:
    row = await db.scalar(select(Chapter).join(Book, Book.id == Chapter.book_id)
                          .where(Chapter.id == chapter_id, Book.user_id == _uid(user)))
    if row is None:
        raise HTTPException(404, "Chapter not found.")
    return row


async def chunk(db: AsyncSession, chunk_id: int, user: User | int) -> Chunk:
    row = await db.scalar(select(Chunk).join(Book, Book.id == Chunk.book_id)
                          .where(Chunk.id == chunk_id, Book.user_id == _uid(user)))
    if row is None:
        raise HTTPException(404, "Passage not found.")
    return row


async def _own(db: AsyncSession, model, row_id: int, user: User | int, what: str):
    row = await db.scalar(select(model).where(model.id == row_id, model.user_id == _uid(user)))
    if row is None:
        raise HTTPException(404, f"{what} not found.")
    return row


async def conversation(db: AsyncSession, conversation_id: int, user: User | int) -> Conversation:
    return await _own(db, Conversation, conversation_id, user, "Conversation")


async def note(db: AsyncSession, note_id: int, user: User | int) -> Note:
    return await _own(db, Note, note_id, user, "Note")


async def quiz(db: AsyncSession, quiz_id: int, user: User | int) -> Quiz:
    return await _own(db, Quiz, quiz_id, user, "Quiz")


async def flashcard(db: AsyncSession, card_id: int, user: User | int) -> Flashcard:
    return await _own(db, Flashcard, card_id, user, "Flashcard")


async def entity(db: AsyncSession, entity_id: int, user: User | int) -> Entity:
    return await _own(db, Entity, entity_id, user, "Entity")
