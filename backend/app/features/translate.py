"""Side-by-side translation of a chapter, paragraph by paragraph, cached per (chapter, language).

Paragraphs are chapter.text split on blank lines, the same split the reader renders, so the
translation lines up with the original. Runs as a background job; the reader polls it.
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Translation
from app.db.session import SessionLocal
from app.features.common import max_input_chars, parallel_requests
from app.features.jobs import JobContext
from app.llm import client as llm
from app.llm.prompts import translate as P

LANGUAGE = re.compile(r"^[^\W\d_][\w\s()'.\-]{1,39}$")


def job_kind(chapter_id: int, language: str) -> str:
    # feature_jobs.kind is 30 chars; the language name can be longer.
    return f"tr:{chapter_id}:{hashlib.sha1(language.lower().encode()).hexdigest()[:8]}"


def paragraphs_of(text: str) -> list[str]:
    return text.split("\n\n")


def needs_translation(p: str) -> bool:
    """Scene breaks ("* * *"), page numbers, empty lines: copy as they are."""
    return sum(ch.isalpha() for ch in p) >= 2


def batches(paras: list[str], budget: int) -> list[list[int]]:
    """Group paragraph indexes into requests of at most ~budget characters (a long paragraph goes alone)."""
    out: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i, p in enumerate(paras):
        if not needs_translation(p):
            continue
        if cur and size + len(p) > budget:
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(p)
    if cur:
        out.append(cur)
    return out


async def cached(db: AsyncSession, chapter_id: int, language: str) -> Translation | None:
    return await db.scalar(select(Translation).where(
        Translation.chapter_id == chapter_id, Translation.language == language))


async def _translate_batch(paras: list[str], idx: list[int], language: str) -> dict[int, str]:
    numbered = [(k + 1, paras[i]) for k, i in enumerate(idx)]
    out = await llm.complete_json(P.system(language), P.build_user(numbered, language), P.TranslationOut,
                                  max_tokens=12000)
    got = {k: p.text.strip() for p in out.paragraphs if 1 <= (k := p.n) <= len(idx) and p.text.strip()}
    return {idx[k - 1]: text for k, text in got.items()}


def translation_job(book_id: int, chapter_id: int, language: str):
    async def work(ctx: JobContext) -> None:
        async with SessionLocal() as db:
            chapter = await db.get(Chapter, chapter_id)
            paras = paragraphs_of(chapter.text)
        # Output is about as long as input: keep requests small enough to finish within the output limit.
        groups = batches(paras, budget=max(1200, min(5000, max_input_chars() // 4)))
        result = list(paras)  # untranslatable bits (and, as a last resort, failures) keep the original
        done = 0
        sem = asyncio.Semaphore(parallel_requests())

        async def run(idx: list[int]) -> None:
            nonlocal done
            async with sem:
                got = await _translate_batch(paras, idx, language)
                # Paragraphs the model skipped: ask again one at a time.
                for i in idx:
                    if i not in got:
                        try:
                            got.update(await _translate_batch(paras, [i], language))
                        except llm.LLMError:
                            pass  # keep the original paragraph rather than fail the whole chapter
                for i, text in got.items():
                    result[i] = text
                done += 1
                await ctx.progress(done / max(len(groups), 1))

        await asyncio.gather(*(run(g) for g in groups))
        async with SessionLocal() as db:
            await db.execute(delete(Translation).where(
                Translation.chapter_id == chapter_id, Translation.language == language))
            db.add(Translation(book_id=book_id, chapter_id=chapter_id, language=language, paragraphs=result,
                               model=llm.provider().model))
            await db.commit()

    return work
