"""Book memory: a short summary of every chapter, sent with each chat question.

The passages found by search give exact wording and citations; the memory gives the model the
whole story (who, what, in which order), so whole-book questions and "why" questions that depend
on earlier chapters can be answered. The summaries are the cached "short" chapter summaries the
Summaries tab also uses, written once per book on the light model (so a cloud provider's small
free daily quota on the main model is kept for answers).
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, Chapter, Summary
from app.db.session import SessionLocal
from app.features.common import parallel_requests
from app.features.jobs import JobContext
from app.features.summaries import _summarize_text
from app.llm import client as llm

JOB_KIND = "memory"
LENGTH = "short"
TINY_CHAPTER = 600  # covers, dedications...: kept as they are, no AI request needed


async def chapter_memories(db: AsyncSession, book_id: int, max_chapter: int | None = None) -> list[tuple[str, str | None]]:
    """(chapter title, memory or None if not written yet) in reading order, within the spoiler limit."""
    stmt = select(Chapter.id, Chapter.title).where(Chapter.book_id == book_id).order_by(Chapter.position)
    if max_chapter is not None:
        stmt = stmt.where(Chapter.position <= max_chapter)
    chapters = (await db.execute(stmt)).all()
    memories: dict[int, str] = {}
    for cid, content in (await db.execute(
            select(Summary.chapter_id, Summary.content)
            .where(Summary.book_id == book_id, Summary.length == LENGTH, Summary.chapter_id.is_not(None))
            .order_by(Summary.id))).all():
        memories[cid] = content  # ordered by id: the newest summary of a chapter wins
    return [(title, memories.get(cid)) for cid, title in chapters]


async def status(db: AsyncSession, book_id: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id))
    done = await db.scalar(
        select(func.count(func.distinct(Summary.chapter_id)))
        .join(Chapter, Chapter.id == Summary.chapter_id)
        .where(Chapter.book_id == book_id, Summary.length == LENGTH))
    return {"chapters": total or 0, "done": done or 0}


def memory_job(book_id: int):
    """Background job: write the missing chapter summaries, several at once on cloud models."""

    async def work(ctx: JobContext) -> None:
        async with SessionLocal() as db:
            book = await db.get(Book, book_id)
            if book is None:
                return
            have = set((await db.execute(
                select(Summary.chapter_id).where(Summary.book_id == book_id, Summary.length == LENGTH,
                                                 Summary.chapter_id.is_not(None)))).scalars())
            todo = [(c.id, c.title, c.text) for c in (await db.execute(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position))).scalars()
                if c.id not in have]
            title = book.title
        if not todo:
            return
        model = llm.provider().fast_model
        sem = asyncio.Semaphore(parallel_requests())
        done = 0

        async def one(cid: int, ctitle: str, text: str) -> None:
            nonlocal done
            async with sem:
                if len(text) < TINY_CHAPTER:
                    content = " ".join(text.split())
                else:
                    content = await _summarize_text(title, ctitle, text, LENGTH, model=model)
                async with SessionLocal() as db:
                    db.add(Summary(book_id=book_id, chapter_id=cid, length=LENGTH, content=content.strip()))
                    await db.commit()
                done += 1
                await ctx.progress(done / len(todo))

        await asyncio.gather(*(one(*c) for c in todo))

    return work
