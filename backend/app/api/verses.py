"""Chapter and verse navigation for books with verses (see ingestion/verses.py).

Every lookup goes through the ownership checks: someone else's book or chapter is a 404, exactly
like one that doesn't exist.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import scope
from app.auth.deps import CurrentUser, current_user
from app.db.models import Chapter, Verse
from app.db.session import get_db
from app.ingestion.verses import parse_reference, resolve_book

router = APIRouter(prefix="/api", tags=["verses"], dependencies=[Depends(current_user)])

EXAMPLES = "Try “John 3:16”, “Gen 1:3” or “3:16”."


async def chapter_verses(db: AsyncSession, chapter_id: int) -> list[dict]:
    """A chapter's verses: where each one is in the chapter text (the text itself is the chapter's)."""
    rows = (await db.execute(
        select(Verse.number, Verse.end, Verse.kind, Verse.char_start, Verse.char_end)
        .where(Verse.chapter_id == chapter_id).order_by(Verse.position)
    )).all()
    return [{"number": n, "end": e, "kind": k, "start": s, "stop": t} for n, e, k, s, t in rows]


@router.get("/books/{book_id}/verses/lookup")
async def lookup(user: CurrentUser, book_id: int, ref: str = Query(min_length=1, max_length=100),
                 from_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    """Where a reference such as "John 3:16", "Gen 1:3-5", "Ps 23" or "3:16" is in this book.
    Without a book name, the reference is in the book of `from_chapter` (the one on screen)."""
    book = await scope.book(db, book_id, user)
    if book.verse_summary is None:
        raise HTTPException(400, "This book has no chapter and verse numbers.")
    parsed = parse_reference(ref)
    if parsed is None:
        raise HTTPException(422, f"“{ref}” doesn't look like a reference. {EXAMPLES}")
    sections = list((await db.execute(
        select(Chapter.section).where(Chapter.book_id == book.id, Chapter.section.is_not(None))
        .group_by(Chapter.section).order_by(func.min(Chapter.position))
    )).scalars())

    if parsed.book:
        section = resolve_book(parsed.book, sections)
        if section is None:
            raise HTTPException(404, f"No book called “{parsed.book}” in “{book.title}”. {EXAMPLES}")
    else:
        here = None
        if from_chapter:
            here = await db.scalar(select(Chapter.section).where(Chapter.id == from_chapter, Chapter.book_id == book.id))
        section = here or (sections[0] if len(sections) == 1 else None)
        if section is None:
            raise HTTPException(422, f"Say which book, e.g. “John {ref.strip()}”.")

    number = parsed.chapter or 1
    chapter = await db.scalar(select(Chapter).where(
        Chapter.book_id == book.id, Chapter.section == section, Chapter.number == number))
    if chapter is None:
        last = await db.scalar(select(func.max(Chapter.number)).where(Chapter.book_id == book.id, Chapter.section == section))
        raise HTTPException(404, f"{section} has no chapter {number} (its last chapter is {last}).")

    out = {"chapter_id": chapter.id, "title": chapter.title, "section": section, "chapter": number,
           "verse": None, "verse_end": None, "start": None, "end": None}
    if parsed.verse is None:
        return out
    verses = await chapter_verses(db, chapter.id)
    numbered = [v for v in verses if v["kind"] == "verse"]

    def covering(n: int) -> dict | None:
        return next((v for v in numbered if v["number"] <= n <= (v["end"] or v["number"])), None)

    first = covering(parsed.verse)
    if first is None:
        last_verse = max(((v["end"] or v["number"]) for v in numbered), default=0)
        why = f"its last verse is {last_verse}" if parsed.verse > last_verse else "this translation leaves it out"
        raise HTTPException(404, f"{chapter.title} has no verse {parsed.verse} ({why}).")
    last = (covering(parsed.verse_end) if parsed.verse_end else None) or first
    out.update(verse=parsed.verse, verse_end=parsed.verse_end, start=first["start"], end=last["stop"])
    return out
