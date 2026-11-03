"""Search the whole library: passage search across every indexed book, and an AI answer drawn from all of them."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import cited_markers, source_dict, sse
from app.db.models import Book
from app.db.session import SessionLocal, get_db
from app.llm import client as llm
from app.llm.prompts import chat as chat_prompts
from app.retrieval.hybrid import Passage, search_books

log = logging.getLogger("bookmind")
router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryQuery(BaseModel):
    q: str = Field(min_length=2, max_length=1000)
    # Spoiler guard per book ({book_id: last chapter read}); books not listed have no limit.
    max_chapters: dict[int, int] = Field(default_factory=dict)
    book_ids: list[int] = Field(default_factory=list)  # empty = every ready book
    style: str = "default"


async def _ready_ids(db: AsyncSession, wanted: list[int]) -> list[int]:
    stmt = select(Book.id).where(Book.status == "ready").order_by(Book.id)
    if wanted:
        stmt = stmt.where(Book.id.in_(wanted))
    ids = list((await db.execute(stmt)).scalars())
    if not ids:
        raise HTTPException(409, "No indexed books to search yet. Add a book and wait for it to finish indexing.")
    return ids


async def _search(db: AsyncSession, req: LibraryQuery, per_book_k: int) -> list[Passage]:
    ids = await _ready_ids(db, req.book_ids)
    found = await search_books(db, req.q, ids, {b: req.max_chapters.get(b) for b in ids}, per_book_k=per_book_k)
    # Re-ranker scores share one scale for a given query, so books can be merged by score.
    return sorted(found, key=lambda p: p.score, reverse=True)


@router.post("/search")
async def search_library(req: LibraryQuery, db: AsyncSession = Depends(get_db)):
    passages = await _search(db, req, per_book_k=4)
    return {"query": req.q, "results": [source_dict(i, p) for i, p in enumerate(passages[:30], start=1)]}


@router.post("/ask")
async def ask_library(req: LibraryQuery, db: AsyncSession = Depends(get_db)):
    """One-off question answered from passages across the library (not saved as a conversation)."""
    if not llm.llm_configured():
        raise HTTPException(503, llm.not_configured_message())
    if req.style not in chat_prompts.STYLES:
        raise HTTPException(400, f"Unknown style. Options: {', '.join(chat_prompts.STYLES)}")
    ids = await _ready_ids(db, req.book_ids)

    async def stream():
        answer = ""
        try:
            yield sse("status", {"stage": "searching"})
            async with SessionLocal() as sdb:
                found = await _search(sdb, req, per_book_k=4)
            passages = found[: llm.provider().default_top_k]
            sources = [source_dict(i, p) for i, p in enumerate(passages, start=1)]
            yield sse("sources", {"query": req.q, "sources": sources})
            yield sse("status", {"stage": "answering"})
            system = chat_prompts.build_system(req.style, None, len(ids) > 1, None)
            async for delta in llm.stream_text(system, [
                {"role": "user", "content": chat_prompts.build_user_turn(req.q, passages)}]):
                answer += delta
                yield sse("delta", {"text": delta})
            used = [] if chat_prompts.is_not_found(answer) else cited_markers(answer, len(passages))
            yield sse("done", {"message_id": None, "cited": used})
        except llm.LLMError as e:
            yield sse("error", {"message": e.message, "partial": answer})
        except Exception as e:  # noqa: BLE001
            log.exception("Library answer failed")
            yield sse("error", {"message": f"Something went wrong while answering: {e}", "partial": answer})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
