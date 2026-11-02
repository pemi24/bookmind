"""Quote finder: verbatim quotes about a topic, with exact locations.

Hybrid retrieval finds candidate passages; the model picks quotes; every quote is then
VERIFIED against the stored passage text (find_verbatim) and dropped if it isn't really
there, so the user never sees an invented "quote".
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.common import find_verbatim, max_input_chars
from app.ingestion.chunking import page_at
from app.db.models import Chapter
from app.llm import client as llm
from app.llm.prompts import quotes as P
from app.retrieval.hybrid import search_book


async def find_quotes(db: AsyncSession, book_id: int, book_title: str, topic: str,
                      max_chapter: int | None, limit: int = 8) -> list[dict]:
    # As many candidate passages as fit the model's context (12 for cloud models).
    passages = await search_book(db, topic, book_id, max_chapter=max_chapter,
                                 top_k=max(3, min(12, max_input_chars() // 2200)))
    if not passages:
        return []
    picked = await llm.complete_json(
        P.SYSTEM, P.build_user(topic, [p.text for p in passages], limit), P.QuotesOut, max_tokens=8000,
    )
    chapters: dict[int, Chapter] = {}
    out, seen = [], set()
    for q in picked.quotes:
        if not 1 <= q.passage <= len(passages):
            continue
        p = passages[q.passage - 1]
        loc = find_verbatim(p.text, q.quote)
        if loc is None:
            continue  # not verbatim: drop it
        start, end = p.char_start + loc[0], p.char_start + loc[1]
        if (p.chapter_id, start) in seen:
            continue
        seen.add((p.chapter_id, start))
        if p.chapter_id not in chapters:
            chapters[p.chapter_id] = await db.get(Chapter, p.chapter_id)
        ch = chapters[p.chapter_id]
        out.append({
            "quote": ch.text[start:end],  # the book's exact text, not the model's copy
            "note": q.note, "chunk_id": p.chunk_id, "chapter_id": p.chapter_id,
            "chapter_position": p.chapter_position, "chapter_title": p.chapter_title,
            "page": page_at(ch.page_map, start), "char_start": start, "char_end": end,
            "book_title": book_title,
        })
    return out[:limit]
