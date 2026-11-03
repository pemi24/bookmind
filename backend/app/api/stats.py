"""Reading stats: the reader reports active reading time; the stats page reads the totals."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.books import get_book_or_404
from app.db.session import get_db
from app.features import stats

router = APIRouter(prefix="/api", tags=["stats"])


class ReadingTime(BaseModel):
    # The reader sends a heartbeat about every 30 s of active reading; cap one report at 5 minutes.
    seconds: int = Field(ge=1, le=300)


@router.post("/books/{book_id}/reading/time", status_code=204)
async def add_reading_time(book_id: int, req: ReadingTime, db: AsyncSession = Depends(get_db)):
    await get_book_or_404(db, book_id)
    await stats.add_activity(db, book_id, seconds=req.seconds)
    await db.commit()


@router.get("/stats")
async def reading_stats(days: int = 30, db: AsyncSession = Depends(get_db)):
    return await stats.compute(db, min(max(days, 7), 365))
