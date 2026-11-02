"""Library + reader endpoints: upload, list, delete, re-index, progress (SSE), chapters, chunks."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Book, Chapter, Chunk
from app.db.session import SessionLocal, get_db
from app.ingestion.chunking import page_at
from app.ingestion.parsers import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import schedule_ingestion, title_from_filename
from app.retrieval.hybrid import search_book

router = APIRouter(prefix="/api", tags=["books"])


def book_dict(b: Book, chapter_count: int | None = None) -> dict:
    return {
        "id": b.id, "title": b.title, "author": b.author, "filename": b.filename,
        "file_type": b.file_type, "file_size": b.file_size, "page_count": b.page_count,
        "pages_estimated": b.pages_estimated, "is_fiction": b.is_fiction,
        "status": b.status, "progress": b.progress, "status_message": b.status_message,
        "error": b.error, "warnings": b.warnings or [],
        "suggested_questions": b.suggested_questions or [],
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "indexed_at": b.indexed_at.isoformat() if b.indexed_at else None,
        "chapter_count": chapter_count,
    }


async def get_book_or_404(db: AsyncSession, book_id: int) -> Book:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found.")
    return book


@router.get("/books")
async def list_books(db: AsyncSession = Depends(get_db)):
    counts = dict((await db.execute(
        select(Chapter.book_id, func.count()).group_by(Chapter.book_id)
    )).all())
    books = (await db.execute(select(Book).order_by(Book.created_at.desc()))).scalars().all()
    return [book_dict(b, counts.get(b.id, 0)) for b in books]


@router.get("/books/{book_id}")
async def get_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await get_book_or_404(db, book_id)
    n = await db.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id))
    return book_dict(book, n)


@router.post("/books", status_code=201)
async def upload_book(file: UploadFile, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    name = Path(file.filename or "book").name
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type '{ext or '?'}'. Upload a PDF, EPUB, DOCX, TXT or MD file.")

    limit = s.max_upload_mb * 1024 * 1024
    dest = s.upload_dir / f"{uuid.uuid4().hex}{ext}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File is larger than the {s.max_upload_mb} MB limit (MAX_UPLOAD_MB).")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")

    title = title_from_filename(name)
    book = Book(
        title=title, filename=name, file_path=str(dest), file_type=ext.lstrip("."),
        file_size=size, status="pending", status_message="Queued", warnings=[], suggested_questions=[],
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    schedule_ingestion(book.id)
    return book_dict(book, 0)


@router.delete("/books/{book_id}", status_code=204)
async def delete_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await get_book_or_404(db, book_id)
    if book.status == "processing":
        raise HTTPException(409, "This book is being indexed. Wait for it to finish, then delete it.")
    path = Path(book.file_path)
    await db.delete(book)  # ON DELETE CASCADE removes chapters, chunks, chats, notes...
    await db.commit()
    path.unlink(missing_ok=True)


@router.post("/books/{book_id}/reindex", status_code=202)
async def reindex_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await get_book_or_404(db, book_id)
    if book.status in ("processing", "pending"):
        raise HTTPException(409, "This book is already queued or indexing.")
    book.status, book.progress, book.status_message, book.error = "pending", 0.0, "Queued", None
    await db.commit()
    schedule_ingestion(book_id)
    return {"ok": True}


@router.get("/books/{book_id}/progress")
async def book_progress(book_id: int, request: Request):
    """Server-Sent Events stream of indexing progress until the book is ready/failed."""

    async def events():
        last = None
        while not await request.is_disconnected():
            async with SessionLocal() as db:
                book = await db.get(Book, book_id)
                if book is None:
                    yield "event: error\ndata: {\"message\": \"Book not found\"}\n\n"
                    return
                payload = {"status": book.status, "progress": round(book.progress or 0, 4),
                           "message": book.status_message, "error": book.error}
            if payload != last:
                yield f"data: {json.dumps(payload)}\n\n"
                last = payload
            if payload["status"] in ("ready", "failed"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/books/{book_id}/chapters")
async def list_chapters(book_id: int, db: AsyncSession = Depends(get_db)):
    await get_book_or_404(db, book_id)
    rows = (await db.execute(
        select(Chapter.id, Chapter.position, Chapter.title, Chapter.start_page, Chapter.end_page,
               func.length(Chapter.text))
        .where(Chapter.book_id == book_id).order_by(Chapter.position)
    )).all()
    return [{"id": r[0], "position": r[1], "title": r[2], "start_page": r[3], "end_page": r[4], "chars": r[5]}
            for r in rows]


@router.get("/chapters/{chapter_id}")
async def get_chapter(chapter_id: int, db: AsyncSession = Depends(get_db)):
    ch = await db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(404, "Chapter not found.")
    return {"id": ch.id, "book_id": ch.book_id, "position": ch.position, "title": ch.title,
            "text": ch.text, "page_map": ch.page_map, "start_page": ch.start_page, "end_page": ch.end_page}


@router.get("/books/{book_id}/search")
async def search_text(book_id: int, q: str, limit: int = 200, db: AsyncSession = Depends(get_db)):
    """Exact (case-insensitive) text search for the reader. Returns every occurrence with location."""
    await get_book_or_404(db, book_id)
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(400, "Search for at least 2 characters.")
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    chapters = (await db.execute(
        select(Chapter).where(Chapter.book_id == book_id, Chapter.text.ilike(like, escape="\\"))
        .order_by(Chapter.position)
    )).scalars().all()

    pattern = re.compile(re.escape(q), re.IGNORECASE)
    results, total = [], 0
    for ch in chapters:
        for m in pattern.finditer(ch.text):
            total += 1
            if len(results) >= limit:
                continue
            s, e = m.start(), m.end()
            before = ch.text[max(0, s - 70):s]
            after = ch.text[e:e + 70]
            results.append({
                "chapter_id": ch.id, "chapter_position": ch.position, "chapter_title": ch.title,
                "start": s, "end": e, "page": page_at(ch.page_map, s),
                "before": ("…" if s > 70 else "") + before.replace("\n\n", " "),
                "match": m.group(), "after": after.replace("\n\n", " ") + ("…" if e + 70 < len(ch.text) else ""),
            })
    return {"query": q, "total": total, "results": results}


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: int, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(Chunk, Chapter.title).join(Chapter, Chapter.id == Chunk.chapter_id).where(Chunk.id == chunk_id)
    )).first()
    if row is None:
        raise HTTPException(404, "Passage not found (the book may have been re-indexed).")
    c, title = row
    return {"id": c.id, "book_id": c.book_id, "chapter_id": c.chapter_id, "chapter_position": c.chapter_position,
            "chapter_title": title, "text": c.text, "char_start": c.char_start, "char_end": c.char_end,
            "page_start": c.page_start, "page_end": c.page_end}


@router.get("/books/{book_id}/retrieve")
async def debug_retrieve(book_id: int, q: str, max_chapter: int | None = None, k: int = 8,
                         db: AsyncSession = Depends(get_db)):
    """Inspect hybrid retrieval results directly (used by tests and scripts/eval_retrieval.py)."""
    book = await get_book_or_404(db, book_id)
    if book.status != "ready":
        raise HTTPException(409, "This book is not indexed yet.")
    passages = await search_book(db, q, book_id, max_chapter=max_chapter, top_k=k)
    return [p.to_dict() for p in passages]
