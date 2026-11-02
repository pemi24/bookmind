"""Helpers shared by the feature modules."""
from __future__ import annotations

import random
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, Chapter, Chunk
from app.llm.providers import get_provider


def max_input_chars() -> int:
    """Book text per LLM request; depends on the model's context window (small for local models)."""
    return get_provider().max_input_chars


def parallel_requests() -> int:
    """Concurrent LLM requests for background jobs (a local model handles one at a time)."""
    return 1 if get_provider().local else 3


_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'", "–": "-", "—": "-"})


async def ready_book(db: AsyncSession, book_id: int) -> Book:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found.")
    if book.status != "ready":
        raise HTTPException(409, "This book is not indexed yet.")
    return book


async def allowed_chapters(db: AsyncSession, book_id: int, max_chapter: int | None) -> list[Chapter]:
    """Chapters in reading order, limited by the spoiler guard."""
    stmt = select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
    if max_chapter is not None:
        stmt = stmt.where(Chapter.position <= max_chapter)
    return list((await db.execute(stmt)).scalars())


async def get_chapter(db: AsyncSession, book_id: int, chapter_id: int, max_chapter: int | None) -> Chapter:
    ch = await db.get(Chapter, chapter_id)
    if ch is None or ch.book_id != book_id:
        raise HTTPException(404, "Chapter not found.")
    if max_chapter is not None and ch.position > max_chapter:
        raise HTTPException(403, "Spoiler guard: you haven't reached this chapter yet.")
    return ch


async def sample_chunks(
    db: AsyncSession, book_id: int, chapter_id: int | None, max_chapter: int | None, n: int
) -> list[Chunk]:
    """Passages spread evenly over a chapter, or randomly over the allowed part of the book."""
    stmt = select(Chunk).where(Chunk.book_id == book_id).order_by(Chunk.position)
    if chapter_id is not None:
        stmt = stmt.where(Chunk.chapter_id == chapter_id)
    if max_chapter is not None:
        stmt = stmt.where(Chunk.chapter_position <= max_chapter)
    chunks = list((await db.execute(stmt)).scalars())
    if len(chunks) <= n:
        return chunks
    if chapter_id is not None:
        step = len(chunks) / n
        return [chunks[int(i * step)] for i in range(n)]
    picked = random.sample(chunks, n)
    return sorted(picked, key=lambda c: c.position)


def split_text(text: str, max_chars: int | None = None) -> list[str]:
    """Split at paragraph boundaries into pieces of at most ~max_chars."""
    max_chars = max_chars or max_input_chars()
    if len(text) <= max_chars:
        return [text]
    parts, buf, size = [], [], 0
    for para in text.split("\n\n"):
        if size and size + len(para) > max_chars:
            parts.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 2
    if buf:
        parts.append("\n\n".join(buf))
    return parts


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, unify quotes/dashes, collapse whitespace; keep a map back to original offsets."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text.translate(_QUOTES)):
        if ch.isspace():
            if prev_space or not out:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def find_verbatim(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate `needle` in `haystack` ignoring case, quote style and whitespace differences.

    Returns (start, end) offsets in the ORIGINAL haystack, or None if it isn't really there.
    Used to verify that "quotes" from the LLM are genuinely verbatim.
    """
    needle = needle.strip().strip('"“”').strip()
    if len(needle) < 3:
        return None
    hay_n, hay_idx = _normalize_with_map(haystack)
    ndl_n, _ = _normalize_with_map(needle)
    ndl_n = ndl_n.strip()
    pos = hay_n.find(ndl_n)
    if pos < 0:
        return None
    return hay_idx[pos], hay_idx[pos + len(ndl_n) - 1] + 1


def chunk_for_offset(chunks: list[Chunk], chapter_id: int, offset: int) -> Chunk | None:
    for c in chunks:
        if c.chapter_id == chapter_id and c.char_start <= offset < c.char_end:
            return c
    return None


def normalize_name(name: str) -> str:
    n = name.lower().translate(_QUOTES)
    n = re.sub(r"^(the|a|an)\s+", "", n.strip())
    return re.sub(r"[^\w\s']", "", n).strip()
