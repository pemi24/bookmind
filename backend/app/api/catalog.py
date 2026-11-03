"""Free-book finder: search Project Gutenberg and add a book to the library in one click."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.books import book_dict
from app.db.models import Book
from app.db.session import get_db
from app.features import catalog
from app.ingestion.pipeline import schedule_ingestion

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/search")
async def search_catalog(q: str = "", page: int = 1):
    """Search by title, author or subject. An empty query lists the most downloaded books."""
    try:
        return await catalog.search(q.strip()[:200], min(max(page, 1), 40))
    except catalog.CatalogError as e:
        raise HTTPException(e.status, e.message) from e


class ImportRequest(BaseModel):
    gutenberg_id: int = Field(ge=1)


@router.post("/import", status_code=201)
async def import_from_catalog(req: ImportRequest, db: AsyncSession = Depends(get_db)):
    filename = f"gutenberg-{req.gutenberg_id}"
    existing = await db.scalar(select(Book).where(Book.filename.startswith(filename + ".")))
    if existing is not None:
        raise HTTPException(409, f"“{existing.title}” is already in your library.")
    try:
        got = await catalog.download(req.gutenberg_id)
    except catalog.CatalogError as e:
        raise HTTPException(e.status, e.message) from e
    book = Book(
        title=got["title"][:500], author=(got["author"] or None) and got["author"][:500], filename=got["filename"],
        file_path=str(got["path"]), file_type=got["ext"].lstrip("."), file_size=got["size"],
        status="pending", status_message="Queued", warnings=[], suggested_questions=[],
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    schedule_ingestion(book.id)
    return book_dict(book, 0)
