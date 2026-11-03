"""Free-book finder: search several free-book sources and add a book to the library in one click."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.books import book_dict
from app.db.models import Book
from app.db.session import get_db
from app.features import catalog
from app.ingestion.pipeline import schedule_ingestion, title_from_filename

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

SourceKey = Literal["gutenberg", "standard", "archive"]


@router.get("/sources")
async def list_sources():
    return [{"key": s.key, "name": s.name} for s in catalog.SOURCES]


@router.get("/search")
async def search_catalog(q: str = "", page: int = 1, sources: list[SourceKey] | None = Query(default=None)):
    """Search every source at once (or just `sources`). An empty query lists Gutenberg's most downloaded books."""
    try:
        return await catalog.search(q.strip()[:200], min(max(page, 1), 40), list(sources) if sources else None)
    except catalog.CatalogError as e:
        raise HTTPException(e.status, e.message) from e


class ImportRequest(BaseModel):
    source: SourceKey = "gutenberg"
    id: str | None = Field(default=None, max_length=120)
    gutenberg_id: int | None = Field(default=None, ge=1)  # older clients
    # Shown while the book downloads and indexes; the file's own metadata wins when the source has none.
    title: str | None = Field(default=None, max_length=300)
    author: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _need_id(self):
        if self.id is None and self.gutenberg_id is not None:
            self.source, self.id = "gutenberg", str(self.gutenberg_id)
        if not self.id:
            raise ValueError("id is required")
        return self


@router.post("/import", status_code=201)
async def import_from_catalog(req: ImportRequest, db: AsyncSession = Depends(get_db)):
    prefix = catalog.download_prefix(req.source, req.id)
    existing = await db.scalar(select(Book).where(Book.filename.startswith(prefix)))
    if existing is not None:
        raise HTTPException(409, f"“{existing.title}” is already in your library.")
    try:
        got = await catalog.download(req.source, req.id)
    except catalog.CatalogError as e:
        raise HTTPException(e.status, e.message) from e
    # Sources without metadata (Standard Ebooks) use the search result's title and author.
    title = got["title"] or req.title or title_from_filename(got["filename"])
    author = got["author"] or req.author
    book = Book(
        title=title[:500], author=author[:500] if author else None,
        filename=got["filename"], file_path=str(got["path"]), file_type=got["ext"].lstrip("."), file_size=got["size"],
        status="pending", status_message="Queued", warnings=[], suggested_questions=[],
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    schedule_ingestion(book.id)
    return book_dict(book, 0)
