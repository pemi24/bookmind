"""Chapter and whole-book summaries (short / medium / detailed), cached in `summaries`.

Chapter summaries are generated on request. Whole-book summaries run as a background job:
small books are summarized from the full text in one call; larger ones map-reduce over
(cached) per-chapter summaries. Whole-book summaries respect the spoiler guard: they only
cover chapters 1..N and are cached per N.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Book, Chapter, Summary
from app.db.session import SessionLocal
from app.features.common import allowed_chapters, max_input_chars, parallel_requests, split_text
from app.features.jobs import JobContext
from app.llm import client as llm
from app.llm.prompts import summaries as P

LENGTHS = tuple(P.LENGTHS)


async def cached(db: AsyncSession, book_id: int, chapter_id: int | None, length: str,
                 up_to: int | None) -> Summary | None:
    stmt = select(Summary).where(Summary.book_id == book_id, Summary.length == length)
    stmt = stmt.where(Summary.chapter_id == chapter_id) if chapter_id else stmt.where(Summary.chapter_id.is_(None))
    stmt = stmt.where(Summary.up_to_chapter == up_to) if up_to else stmt.where(Summary.up_to_chapter.is_(None))
    return (await db.execute(stmt.order_by(Summary.id.desc()).limit(1))).scalars().first()


async def _summarize_text(book_title: str, chapter_title: str, text: str, length: str) -> str:
    s = get_settings()
    parts = split_text(text)
    if len(parts) == 1:
        return await llm.complete_text(P.SYSTEM, P.chapter_user(book_title, chapter_title, text, length),
                                       effort=s.llm_task_effort)
    partials = [
        await llm.complete_text(P.SYSTEM, P.part_user(book_title, chapter_title, p, i, len(parts)),
                                model=s.llm_fast_model, effort=s.llm_task_effort)
        for i, p in enumerate(parts, 1)
    ]
    pieces = [(f"Part {i}", t) for i, t in enumerate(partials, 1)]
    return await llm.complete_text(P.SYSTEM, P.combine_user(book_title, f"chapter '{chapter_title}'", pieces,
                                                            length, False), effort=s.llm_task_effort)


async def chapter_summary(db: AsyncSession, book: Book, chapter: Chapter, length: str, refresh: bool) -> Summary:
    if not refresh:
        hit = await cached(db, book.id, chapter.id, length, None)
        if hit:
            return hit
    text = await _summarize_text(book.title, chapter.title, chapter.text, length)
    row = Summary(book_id=book.id, chapter_id=chapter.id, length=length, up_to_chapter=None, content=text)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def book_job(book_id: int, length: str, up_to: int | None):
    """Background job producing a whole-book summary (chapters 1..up_to)."""

    async def work(ctx: JobContext) -> None:
        s = get_settings()
        async with SessionLocal() as db:
            book = await db.get(Book, book_id)
            chapters = await allowed_chapters(db, book_id, up_to)
            title = book.title
            chapter_data = [(c.id, c.title, c.text) for c in chapters]
        if not chapter_data:
            raise llm.LLMError("No chapters to summarize.", 400)
        spoiler = up_to is not None and up_to < (await _chapter_count(book_id))
        scope = "whole book" if not spoiler else f"book up to chapter {up_to}"
        total_chars = sum(len(t) for _, _, t in chapter_data)

        if total_chars <= max_input_chars():
            full = "\n\n".join(f"## {t}\n\n{txt}" for _, t, txt in chapter_data)
            await ctx.progress(0.2)
            content = await llm.complete_text(P.SYSTEM, P.book_user(title, scope, full, length, spoiler),
                                              effort=s.llm_task_effort)
        else:
            # Map: short per-chapter summaries (cached, reused by the chapter view), then reduce.
            sem = asyncio.Semaphore(parallel_requests())
            done = 0

            async def one(cid: int, ctitle: str, ctext: str) -> tuple[str, str]:
                nonlocal done
                async with sem:
                    async with SessionLocal() as db:
                        hit = await cached(db, book_id, cid, "short", None)
                    if hit:
                        text = hit.content
                    else:
                        text = await _summarize_text(title, ctitle, ctext, "short")
                        async with SessionLocal() as db:
                            db.add(Summary(book_id=book_id, chapter_id=cid, length="short", content=text))
                            await db.commit()
                done += 1
                await ctx.progress(0.9 * done / len(chapter_data))
                return ctitle, text

            pieces = await asyncio.gather(*(one(*c) for c in chapter_data))
            content = await llm.complete_text(P.SYSTEM, P.combine_user(title, scope, list(pieces), length, spoiler),
                                              effort=s.llm_task_effort)

        async with SessionLocal() as db:
            db.add(Summary(book_id=book_id, chapter_id=None, length=length, up_to_chapter=up_to, content=content))
            await db.commit()

    return work


async def _chapter_count(book_id: int) -> int:
    async with SessionLocal() as db:
        return len(await allowed_chapters(db, book_id, None))


def job_kind(length: str, up_to: int | None) -> str:
    return f"summary:{length}:{up_to or 'all'}"
