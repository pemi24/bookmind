"""Hybrid retrieval: pgvector similarity + Postgres full-text search, fused with
Reciprocal Rank Fusion, then re-ranked by a cross-encoder.

The spoiler guard is enforced HERE, in SQL (`chapter_position <= max_chapter`), so
passages beyond the reader's progress are never fetched and can't reach the LLM.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Book, Chapter, Chunk, Verse
from app.ingestion.verses import verse_label
from app.retrieval.embeddings import get_embedder
from app.retrieval.rerank import get_reranker


@dataclass
class Passage:
    chunk_id: int
    book_id: int
    book_title: str
    chapter_id: int
    chapter_position: int
    chapter_title: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int
    text: str
    score: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None
    # Books with verses: the verses the passage covers, and its text with "3:16" before each verse
    # (for the model, so it can name the exact verse; `text` stays the book's exact text).
    verse_start: int | None = None
    verse_end: int | None = None
    numbered_text: str | None = None

    @property
    def label(self) -> str:
        """How the passage is cited: "Genesis 1:3–5" in a book with verses, else the chapter title."""
        return verse_label(self.chapter_title, self.verse_start, self.verse_end)

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label}


def _keyword_tsquery(query: str) -> str | None:
    """OR-query of the user's words; to_tsquery stems them and drops stopwords."""
    terms = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) > 1]
    terms = list(dict.fromkeys(terms))[:30]
    return " | ".join(terms) if terms else None


def _filters(book_id: int, max_chapter: int | None, user_id: int):
    # Ownership is part of the SQL itself: a book that isn't the user's yields no rows at all.
    conds = [Chunk.book_id == book_id, Chunk.book_id.in_(select(Book.id).where(Book.user_id == user_id))]
    if max_chapter is not None:
        conds.append(Chunk.chapter_position <= max_chapter)
    return conds


async def vector_search(
    db: AsyncSession, qvec: list[float], book_id: int, max_chapter: int | None, limit: int, *, user_id: int
) -> list[int]:
    s = get_settings()
    # Filtered HNSW: iterative scan keeps searching until enough rows pass the WHERE clause.
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(s.hnsw_ef_search)}"))
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    stmt = (
        select(Chunk.id)
        .where(*_filters(book_id, max_chapter, user_id), Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(qvec))
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars())


async def keyword_search(
    db: AsyncSession, query: str, book_id: int, max_chapter: int | None, limit: int, *, user_id: int
) -> list[int]:
    q = _keyword_tsquery(query)
    if not q:
        return []
    tsq = func.to_tsquery("english", q)
    stmt = (
        select(Chunk.id)
        .where(*_filters(book_id, max_chapter, user_id), Chunk.tsv.op("@@")(tsq))
        .order_by(func.ts_rank_cd(Chunk.tsv, tsq, 32).desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars())


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


async def _load_passages(db: AsyncSession, ids: list[int], user_id: int) -> dict[int, Passage]:
    if not ids:
        return {}
    stmt = (
        select(Chunk, Chapter.title, Book.title)
        .join(Chapter, Chapter.id == Chunk.chapter_id)
        .join(Book, Book.id == Chunk.book_id)
        .where(Chunk.id.in_(ids), Book.user_id == user_id)
    )
    out = {}
    for chunk, ch_title, book_title in (await db.execute(stmt)).all():
        out[chunk.id] = Passage(
            chunk_id=chunk.id, book_id=chunk.book_id, book_title=book_title,
            chapter_id=chunk.chapter_id, chapter_position=chunk.chapter_position, chapter_title=ch_title,
            page_start=chunk.page_start, page_end=chunk.page_end,
            char_start=chunk.char_start, char_end=chunk.char_end, text=chunk.text,
            verse_start=chunk.verse_start, verse_end=chunk.verse_end,
        )
    await _number_verses(db, [p for p in out.values() if p.verse_start is not None])
    return out


async def _number_verses(db: AsyncSession, passages: list[Passage]) -> None:
    """Give passages from books with verses their text with each verse's reference ("3:16 For God...")."""
    if not passages:
        return
    rows = (await db.execute(
        select(Verse.chapter_id, Verse.chapter_number, Verse.number, Verse.end, Verse.kind, Verse.char_start, Verse.char_end)
        .where(Verse.chapter_id.in_({p.chapter_id for p in passages})).order_by(Verse.chapter_id, Verse.position)
    )).all()
    for p in passages:
        lines = []
        for ch_id, ch_no, n, end, kind, start, stop in rows:
            if ch_id != p.chapter_id or start < p.char_start or stop > p.char_end:
                continue
            text = p.text[start - p.char_start : stop - p.char_start]
            lines.append(text if kind == "title" else f"{ch_no}:{n}{f'-{end}' if end else ''} {text}")
        p.numbered_text = "\n".join(lines) or None


async def search_book(
    db: AsyncSession,
    query: str,
    book_id: int,
    max_chapter: int | None = None,
    top_k: int | None = None,
    use_rerank: bool = True,
    *,
    user_id: int,
) -> list[Passage]:
    """Hybrid search in one of `user_id`'s books (another user's book gives no results)."""
    s = get_settings()
    if not top_k:
        from app.llm.providers import current_provider  # local import: retrieval doesn't otherwise need the LLM

        top_k = s.retrieval_top_k or current_provider().default_top_k
    qvec = await asyncio.to_thread(get_embedder().embed_query, query)

    vec_ids = await vector_search(db, qvec, book_id, max_chapter, s.retrieval_candidates, user_id=user_id)
    kw_ids = await keyword_search(db, query, book_id, max_chapter, s.retrieval_candidates, user_id=user_id)
    fused = reciprocal_rank_fusion([vec_ids, kw_ids], k=s.rrf_k)
    cand_ids = sorted(fused, key=fused.get, reverse=True)[: s.retrieval_candidates]
    passages = await _load_passages(db, cand_ids, user_id)

    cands = []
    for cid in cand_ids:
        p = passages.get(cid)
        if p is None:
            continue
        p.score = fused[cid]
        p.vector_rank = vec_ids.index(cid) + 1 if cid in vec_ids else None
        p.keyword_rank = kw_ids.index(cid) + 1 if cid in kw_ids else None
        cands.append(p)

    reranker = get_reranker() if use_rerank else None
    if reranker and cands:
        # The cross-encoder dominates search time on a CPU, so only the best fused candidates are re-read.
        head = cands[: max(s.rerank_candidates, top_k)]
        scores = await asyncio.to_thread(reranker.score, query, [p.text for p in head])
        for p, sc in zip(head, scores):
            p.score = sc
        head.sort(key=lambda p: p.score, reverse=True)
        cands = head
    return cands[:top_k]


async def search_books(
    db: AsyncSession,
    query: str,
    book_ids: list[int],
    max_chapters: dict[int, int | None] | None = None,
    per_book_k: int = 5,
    *,
    user_id: int,
) -> list[Passage]:
    """Compare mode: retrieve separately per book so every book is represented (only `user_id`'s books)."""
    max_chapters = max_chapters or {}
    out: list[Passage] = []
    for bid in book_ids:
        out.extend(await search_book(db, query, bid, max_chapters.get(bid), top_k=per_book_k, user_id=user_id))
    return out
