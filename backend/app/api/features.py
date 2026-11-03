"""Summaries, Explorer (entities/relations), Timeline, Quote finder, background jobs.

Every endpoint takes an optional `max_chapter` (spoiler guard) and never returns
anything first appearing after that chapter.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chapter, Chunk, Entity, EntityRelation, TimelineEvent
from app.db.session import get_db
from app.features import analysis, essay, memory, quotes, summaries, translate
from app.features.common import get_chapter, ready_book
from app.features.jobs import is_running, job_dict, latest_job, start_job
from app.llm.client import llm_configured, not_configured_message

router = APIRouter(prefix="/api", tags=["features"])

Length = Literal["short", "medium", "detailed"]


def require_llm() -> None:
    if not llm_configured():
        raise HTTPException(503, not_configured_message())


async def effective_max_chapter(db: AsyncSession, book_id: int, max_chapter: int | None) -> int | None:
    """None when the limit covers the whole book (so 'all chapters' caches are shared)."""
    if max_chapter is None:
        return None
    if max_chapter < 1:
        raise HTTPException(400, "max_chapter must be at least 1.")
    total = await db.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id))
    return None if max_chapter >= (total or 0) else max_chapter


# ---------------------------------------------------------------- summaries

class SummaryRequest(BaseModel):
    chapter_id: int | None = None  # None = whole book
    length: Length = "medium"
    max_chapter: int | None = None
    refresh: bool = False


def _summary_dict(s) -> dict:
    return {"id": s.id, "chapter_id": s.chapter_id, "length": s.length, "up_to_chapter": s.up_to_chapter,
            "content": s.content, "created_at": s.created_at.isoformat() if s.created_at else None}


@router.post("/books/{book_id}/summaries")
async def summarize(book_id: int, req: SummaryRequest, db: AsyncSession = Depends(get_db)):
    book = await ready_book(db, book_id)
    max_ch = await effective_max_chapter(db, book_id, req.max_chapter)
    if req.chapter_id is not None:
        chapter = await get_chapter(db, book_id, req.chapter_id, max_ch)
        if not req.refresh and (hit := await summaries.cached(db, book_id, chapter.id, req.length, None)):
            return {"status": "done", "summary": _summary_dict(hit)}
        require_llm()
        row = await summaries.chapter_summary(db, book, chapter, req.length, req.refresh)
        return {"status": "done", "summary": _summary_dict(row)}

    kind = summaries.job_kind(req.length, max_ch)
    if not req.refresh and (hit := await summaries.cached(db, book_id, None, req.length, max_ch)):
        return {"status": "done", "summary": _summary_dict(hit)}
    require_llm()
    job = await start_job(book_id, kind, summaries.book_job(book_id, req.length, max_ch))
    return {"status": "running", "job": job}


@router.get("/books/{book_id}/summaries")
async def get_summary(book_id: int, length: Length = "medium", chapter_id: int | None = None,
                      max_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    """Cached summary if available, else the status of the job producing it."""
    await ready_book(db, book_id)
    max_ch = await effective_max_chapter(db, book_id, max_chapter)
    if chapter_id is not None:
        await get_chapter(db, book_id, chapter_id, max_ch)
    hit = await summaries.cached(db, book_id, chapter_id, length, None if chapter_id else max_ch)
    if hit:
        return {"status": "done", "summary": _summary_dict(hit)}
    if chapter_id is None:
        job = await latest_job(db, book_id, summaries.job_kind(length, max_ch))
        if job and (job.status == "failed" or is_running(book_id, job.kind)):
            return {"status": job.status if job.status == "failed" else "running", "job": job_dict(job)}
    return {"status": "missing"}


# ---------------------------------------------------------------- analysis: explorer + timeline

@router.post("/books/{book_id}/analysis", status_code=202)
async def start_analysis(book_id: int, db: AsyncSession = Depends(get_db)):
    await ready_book(db, book_id)
    require_llm()
    return await start_job(book_id, analysis.JOB_KIND, analysis.analysis_job(book_id))


async def _analysis_status(db: AsyncSession, book_id: int) -> dict | None:
    job = await latest_job(db, book_id, analysis.JOB_KIND)
    d = job_dict(job)
    if d and d["status"] == "running" and not is_running(book_id, analysis.JOB_KIND):
        d["status"] = "failed"
        d["error"] = d["error"] or "Interrupted. Start it again."
    return d


@router.get("/books/{book_id}/entities")
async def list_entities(book_id: int, max_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    await ready_book(db, book_id)
    max_ch = await effective_max_chapter(db, book_id, max_chapter)
    stmt = select(Entity).where(Entity.book_id == book_id)
    rstmt = select(EntityRelation).where(EntityRelation.book_id == book_id)
    if max_ch is not None:
        stmt = stmt.where(Entity.first_chapter <= max_ch)
        rstmt = rstmt.where(EntityRelation.first_chapter <= max_ch)
    ents = list((await db.execute(stmt.order_by(Entity.importance.desc(), Entity.name))).scalars())
    visible = {e.id for e in ents}
    rels = [r for r in (await db.execute(rstmt)).scalars() if r.source_id in visible and r.target_id in visible]

    def details(e: Entity) -> list[dict]:
        return [d for d in (e.details or []) if max_ch is None or d["chapter"] <= max_ch]

    return {
        "job": await _analysis_status(db, book_id),
        "entities": [{"id": e.id, "kind": e.kind, "name": e.name, "aliases": e.aliases, "importance": e.importance,
                      "first_chapter": e.first_chapter, "details": details(e),
                      "description": (details(e) or [{"text": e.description}])[0]["text"]} for e in ents],
        "relations": [{"id": r.id, "source": r.source_id, "target": r.target_id, "relation": r.relation,
                       "description": r.description, "first_chapter": r.first_chapter} for r in rels],
    }


@router.get("/entities/{entity_id}/mentions")
async def entity_mentions(entity_id: int, max_chapter: int | None = None, limit: int = 12,
                          db: AsyncSession = Depends(get_db)):
    ent = await db.get(Entity, entity_id)
    if ent is None:
        raise HTTPException(404, "Entity not found.")
    max_ch = await effective_max_chapter(db, ent.book_id, max_chapter)
    names = [n for n in {ent.name, *ent.aliases} if len(n) >= 2]
    conds = [Chunk.text.ilike("%" + n.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\") for n in names]
    stmt = (select(Chunk, Chapter.title).join(Chapter, Chapter.id == Chunk.chapter_id)
            .where(Chunk.book_id == ent.book_id, or_(*conds)).order_by(Chunk.position).limit(limit))
    if max_ch is not None:
        stmt = stmt.where(Chunk.chapter_position <= max_ch)
    rows = (await db.execute(stmt)).all()
    return [{"chunk_id": c.id, "chapter_id": c.chapter_id, "chapter_position": c.chapter_position,
             "chapter_title": title, "page_start": c.page_start, "char_start": c.char_start, "char_end": c.char_end,
             "text": c.text} for c, title in rows]


@router.get("/books/{book_id}/timeline")
async def timeline(book_id: int, max_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    await ready_book(db, book_id)
    max_ch = await effective_max_chapter(db, book_id, max_chapter)
    stmt = (select(TimelineEvent, Chunk.char_start, Chunk.char_end, Chunk.chapter_id, Chunk.page_start, Chapter.title)
            .outerjoin(Chunk, Chunk.id == TimelineEvent.chunk_id)
            .outerjoin(Chapter, Chapter.id == Chunk.chapter_id)
            .where(TimelineEvent.book_id == book_id).order_by(TimelineEvent.position))
    if max_ch is not None:
        stmt = stmt.where(TimelineEvent.chapter_position <= max_ch)
    rows = (await db.execute(stmt)).all()
    return {
        "job": await _analysis_status(db, book_id),
        "events": [{"id": e.id, "position": e.position, "title": e.title, "description": e.description,
                    "when": e.when_label, "chapter_position": e.chapter_position, "importance": e.importance,
                    "chunk_id": e.chunk_id, "chapter_id": ch_id, "chapter_title": ch_title, "page": page,
                    "char_start": cs, "char_end": ce}
                   for e, cs, ce, ch_id, page, ch_title in rows],
    }


# ---------------------------------------------------------------- quotes

class QuoteRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    max_chapter: int | None = None
    limit: int = Field(default=8, ge=1, le=15)


@router.post("/books/{book_id}/quotes")
async def quote_finder(book_id: int, req: QuoteRequest, db: AsyncSession = Depends(get_db)):
    book = await ready_book(db, book_id)
    require_llm()
    max_ch = await effective_max_chapter(db, book_id, req.max_chapter)
    found = await quotes.find_quotes(db, book_id, book.title, req.topic, max_ch, req.limit)
    return {"topic": req.topic, "quotes": found}


# ---------------------------------------------------------------- essay helper

class EssayRequest(BaseModel):
    thesis: str = Field(min_length=5, max_length=600)
    max_chapter: int | None = None
    sections: int = Field(default=3, ge=2, le=5)


@router.post("/books/{book_id}/essay")
async def essay_outline(book_id: int, req: EssayRequest, db: AsyncSession = Depends(get_db)):
    book = await ready_book(db, book_id)
    require_llm()
    max_ch = await effective_max_chapter(db, book_id, req.max_chapter)
    return await essay.outline(db, book, req.thesis.strip(), max_ch, req.sections)


class EssayExport(BaseModel):
    essay: dict


@router.post("/books/{book_id}/essay/export")
async def essay_export(book_id: int, req: EssayExport, db: AsyncSession = Depends(get_db)):
    """The outline as a Markdown file (the browser already has the outline; this just formats it)."""
    book = await ready_book(db, book_id)
    try:
        md = essay.to_markdown(book, req.essay)
    except (KeyError, TypeError) as e:
        raise HTTPException(400, "That isn't an essay outline from BookMind.") from e
    return Response(md, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="essay-outline.md"'})


# ---------------------------------------------------------------- side-by-side translation

def _language(value: str) -> str:
    lang = " ".join(value.split())
    if not translate.LANGUAGE.match(lang):
        raise HTTPException(400, "Give a language name, e.g. French, Spanish or Brazilian Portuguese.")
    return lang


async def _translation_state(db: AsyncSession, chapter: Chapter, language: str) -> dict:
    hit = await translate.cached(db, chapter.id, language)
    if hit is not None:
        return {"status": "done", "language": language, "paragraphs": hit.paragraphs}
    job = job_dict(await latest_job(db, chapter.book_id, translate.job_kind(chapter.id, language)))
    return {"status": job["status"] if job else "none", "language": language, "job": job}


@router.get("/chapters/{chapter_id}/translation")
async def get_translation(chapter_id: int, language: str, db: AsyncSession = Depends(get_db)):
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404, "Chapter not found.")
    return await _translation_state(db, chapter, _language(language))


class TranslateRequest(BaseModel):
    language: str = Field(min_length=2, max_length=40)


@router.post("/chapters/{chapter_id}/translation")
async def start_translation(chapter_id: int, req: TranslateRequest, db: AsyncSession = Depends(get_db)):
    """Translate a chapter in the background (or return the saved translation)."""
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404, "Chapter not found.")
    language = _language(req.language)
    state = await _translation_state(db, chapter, language)
    if state["status"] in ("done", "running"):
        return state
    require_llm()
    job = await start_job(chapter.book_id, translate.job_kind(chapter.id, language),
                          translate.translation_job(chapter.book_id, chapter.id, language))
    return {"status": "running", "language": language, "job": job}


# ---------------------------------------------------------------- book memory

@router.get("/books/{book_id}/memory")
async def memory_status(book_id: int, db: AsyncSession = Depends(get_db)):
    """How many chapters have a memory summary, and the job writing them (if any)."""
    await ready_book(db, book_id)
    return {**await memory.status(db, book_id), "job": job_dict(await latest_job(db, book_id, memory.JOB_KIND))}


@router.post("/books/{book_id}/memory", status_code=202)
async def build_memory(book_id: int, db: AsyncSession = Depends(get_db)):
    """Write the missing chapter summaries (books added before book memory existed, or after a failure)."""
    await ready_book(db, book_id)
    require_llm()
    job = await start_job(book_id, memory.JOB_KIND, memory.memory_job(book_id))
    return {**await memory.status(db, book_id), "job": job}


@router.get("/books/{book_id}/jobs/{kind}")
async def job_status(book_id: int, kind: str, db: AsyncSession = Depends(get_db)):
    return {"job": job_dict(await latest_job(db, book_id, kind))}
