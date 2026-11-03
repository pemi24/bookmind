"""Notes & highlights: CRUD, tags, export to Markdown / PDF."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.books import get_book_or_404
from app.db.models import Note
from app.db.session import get_db
from app.features import kindle
from app.features import notes as export

router = APIRouter(prefix="/api", tags=["notes"])

Kind = Literal["note", "answer", "passage", "quote"]
Color = Literal["yellow", "green", "blue", "pink"]


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = re.sub(r"[^\w\- ]", "", t.strip().lstrip("#")).strip().lower()[:60]
        if t and t not in out:
            out.append(t)
    return out[:20]


def note_dict(n: Note) -> dict:
    return {"id": n.id, "book_id": n.book_id, "kind": n.kind, "title": n.title, "content": n.content,
            "chunk_id": n.chunk_id, "message_id": n.message_id, "location": n.location or {}, "tags": n.tags or [],
            "color": n.color, "comment": n.comment, "created_at": n.created_at.isoformat() if n.created_at else None}


class NoteCreate(BaseModel):
    kind: Kind = "note"
    title: str | None = Field(default=None, max_length=300)
    content: str = Field(min_length=1, max_length=50_000)
    chunk_id: int | None = None
    message_id: int | None = None
    location: dict = Field(default_factory=dict)  # chapter_id, chapter_title, page, char_start, char_end
    tags: list[str] = Field(default_factory=list)
    color: Color | None = None
    comment: str | None = Field(default=None, max_length=10_000)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=50_000)
    tags: list[str] | None = None
    color: Color | None = None
    comment: str | None = Field(default=None, max_length=10_000)  # "" clears it


@router.post("/books/{book_id}/notes", status_code=201)
async def create_note(book_id: int, req: NoteCreate, db: AsyncSession = Depends(get_db)):
    await get_book_or_404(db, book_id)
    note = Note(book_id=book_id, kind=req.kind, title=req.title, content=req.content, chunk_id=req.chunk_id,
                message_id=req.message_id, location=req.location, tags=_clean_tags(req.tags),
                color=req.color, comment=(req.comment or "").strip() or None)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note_dict(note)


async def _notes(db: AsyncSession, book_id: int, tag: str | None) -> list[Note]:
    stmt = select(Note).where(Note.book_id == book_id).order_by(Note.created_at.desc())
    if tag:
        stmt = stmt.where(Note.tags.any(tag.lower()))
    return list((await db.execute(stmt)).scalars())


@router.get("/books/{book_id}/notes")
async def list_notes(book_id: int, tag: str | None = None, db: AsyncSession = Depends(get_db)):
    await get_book_or_404(db, book_id)
    notes = await _notes(db, book_id, tag)
    all_tags = sorted({t for n in await _notes(db, book_id, None) for t in (n.tags or [])})
    return {"notes": [note_dict(n) for n in notes], "tags": all_tags}


_CLIPPINGS_MAX_BYTES = 20 * 1024 * 1024


async def _read_clippings(file: UploadFile) -> list[kindle.Clipping]:
    raw = await file.read(_CLIPPINGS_MAX_BYTES + 1)
    if len(raw) > _CLIPPINGS_MAX_BYTES:
        raise HTTPException(413, "That file is too large for a Kindle clippings file (20 MB max).")
    clips = kindle.parse_clippings(raw.decode("utf-8-sig", errors="replace"))
    if not clips:
        raise HTTPException(400, "No Kindle highlights found. Choose the “My Clippings.txt” file from your "
                                 "Kindle's documents folder.")
    return clips


@router.post("/books/{book_id}/kindle/preview")
async def kindle_preview(book_id: int, file: UploadFile, db: AsyncSession = Depends(get_db)):
    """Which books are in this clippings file, best match for this book first."""
    book = await get_book_or_404(db, book_id)
    return {"books": kindle.summarize(await _read_clippings(file), book.title)}


@router.post("/books/{book_id}/kindle/import")
async def kindle_import(book_id: int, file: UploadFile, kindle_title: str = Form(...),
                        db: AsyncSession = Depends(get_db)):
    """Import one Kindle book's highlights (and the notes typed on them) as highlights of this book."""
    book = await get_book_or_404(db, book_id)
    clips = await _read_clippings(file)
    if not any(c.title == kindle_title for c in clips):
        raise HTTPException(400, "That book isn't in this clippings file.")
    return await kindle.import_clippings(db, book, clips, kindle_title)


@router.get("/books/{book_id}/highlights")
async def chapter_highlights(book_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    """Saved notes that point at a text range in this chapter, for drawing them in the reader."""
    await get_book_or_404(db, book_id)
    loc = Note.location
    rows = (await db.execute(
        select(Note).where(
            Note.book_id == book_id,
            loc["chapter_id"].as_integer() == chapter_id,
            loc["char_end"].as_integer() > loc["char_start"].as_integer(),
        ).order_by(Note.created_at)
    )).scalars()
    return [note_dict(n) for n in rows]


@router.patch("/notes/{note_id}")
async def update_note(note_id: int, req: NoteUpdate, db: AsyncSession = Depends(get_db)):
    note = await db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Note not found.")
    if req.title is not None:
        note.title = req.title or None
    if req.content is not None:
        note.content = req.content
    if req.tags is not None:
        note.tags = _clean_tags(req.tags)
    if req.color is not None:
        note.color = req.color
    if req.comment is not None:
        note.comment = req.comment.strip() or None
    await db.commit()
    await db.refresh(note)
    return note_dict(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = await db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Note not found.")
    await db.delete(note)
    await db.commit()


@router.get("/books/{book_id}/notes/export")
async def export_notes(book_id: int, format: Literal["md", "pdf"] = "md", tag: str | None = None,
                       db: AsyncSession = Depends(get_db)):
    book = await get_book_or_404(db, book_id)
    notes = list(reversed(await _notes(db, book_id, tag)))  # oldest first reads naturally
    if not notes:
        raise HTTPException(404, "No notes to export.")
    slug = re.sub(r"[^\w]+", "-", book.title.lower()).strip("-")[:60] or "notes"
    if format == "md":
        return Response(export.to_markdown(book, notes), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{slug}-notes.md"'})
    return Response(export.to_pdf(book, notes), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{slug}-notes.pdf"'})
