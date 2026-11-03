"""Import Kindle highlights from "My Clippings.txt" (the file on every Kindle, in /documents).

Each entry looks like:

    The Art of War (Sun Tzu)
    - Your Highlight on page 12 | Location 180-182 | Added on Monday, 1 January 2024 10:00:00

    All warfare is based on deception.
    ==========

Notes typed on the Kindle are separate entries right after the highlight they belong to, at its
end location. Kindles in other languages use translated labels, so detection is keyword-based.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, Chapter, Note
from app.features.common import TextIndex, normalize_name
from app.ingestion.chunking import page_at

_BOOKMARK = re.compile(r"bookmark|signet|lesezeichen|marcador|segnalibro|marcapáginas", re.I)
_HIGHLIGHT = re.compile(r"highlight|surlignement|markierung|subrayado|evidenziazione|destaque|clip", re.I)
_NOTE = re.compile(r"\bnot[ae]\b|notiz|\bnote\b", re.I)
_LOCATION = re.compile(r"(?:location|emplacement|position|posici[oó]n|posizione|posi[cç][aã]o|loc\.)\s*(\d+)(?:\s*-\s*(\d+))?", re.I)
_PAGE = re.compile(r"(?:page|seite|p[aá]gina)\s*(\d+)", re.I)


@dataclass
class Clipping:
    title: str
    author: str | None
    kind: str  # highlight | note
    text: str
    loc_start: int | None
    loc_end: int | None
    page: int | None


def _split_title(line: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", line)
    if m and m.group(1):
        return m.group(1).strip(), m.group(2).strip() or None
    return line.strip(), None


def parse_clippings(raw: str) -> list[Clipping]:
    out: list[Clipping] = []
    for entry in re.split(r"^={5,}\s*$", raw.replace("\r\n", "\n"), flags=re.M):
        lines = [ln.replace("﻿", "") for ln in entry.strip("\n﻿ ").split("\n")]
        if len(lines) < 3:
            continue
        meta, body = lines[1], "\n".join(lines[2:]).strip()
        if not body or _BOOKMARK.search(meta):
            continue
        if _HIGHLIGHT.search(meta):
            kind = "highlight"
        elif _NOTE.search(meta):
            kind = "note"
        else:
            continue
        title, author = _split_title(lines[0])
        loc, page = _LOCATION.search(meta), _PAGE.search(meta)
        start = int(loc.group(1)) if loc else None
        end = int(loc.group(2)) if loc and loc.group(2) else start
        out.append(Clipping(title, author, kind, body, start, end, int(page.group(1)) if page else None))
    return out


def title_score(a: str, b: str) -> float:
    """How likely two titles name the same book (0-1). Kindle titles often add subtitles/series."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def summarize(clips: list[Clipping], book_title: str) -> list[dict]:
    books: dict[str, dict] = {}
    for c in clips:
        b = books.setdefault(c.title, {"title": c.title, "author": c.author, "highlights": 0, "notes": 0})
        b["highlights" if c.kind == "highlight" else "notes"] += 1
    rows = [{**b, "match": round(title_score(book_title, b["title"]), 2)} for b in books.values()]
    return sorted(rows, key=lambda r: (-r["match"], r["title"].lower()))


async def import_clippings(db: AsyncSession, book: Book, clips: list[Clipping], kindle_title: str) -> dict:
    mine = [c for c in clips if c.title == kindle_title]
    highlights = [c for c in mine if c.kind == "highlight"]
    # A Kindle note sits at the end location of the highlight it was typed on.
    notes_by_loc: dict[int, list[str]] = {}
    for c in mine:
        if c.kind == "note" and c.loc_start is not None:
            notes_by_loc.setdefault(c.loc_start, []).append(c.text)

    chapters = list((await db.execute(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position))).scalars())
    indexes = [(ch, TextIndex(ch.text)) for ch in chapters]
    existing = set((await db.execute(
        select(Note.content).where(Note.book_id == book.id, Note.tags.any("kindle")))).scalars())

    imported = located = duplicates = attached = 0
    used_note_locs: set[int] = set()
    for h in highlights:
        if h.text in existing:
            duplicates += 1
            continue
        existing.add(h.text)
        comment_parts = notes_by_loc.get(h.loc_end, []) if h.loc_end is not None else []
        if comment_parts:
            used_note_locs.add(h.loc_end)
            attached += len(comment_parts)
        location: dict = {}
        needle = TextIndex.prepare(h.text)
        for ch, idx in indexes:
            span = idx.find_span(needle)
            if span:
                location = {"chapter_id": ch.id, "chapter_title": ch.title, "page": page_at(ch.page_map, span[0]),
                            "char_start": span[0], "char_end": span[1]}
                located += 1
                break
        if not location and h.page:
            location = {"page": h.page}
        db.add(Note(book_id=book.id, kind="passage", content=h.text, location=location, tags=["kindle"],
                    color="yellow", comment="\n\n".join(comment_parts) or None))
        imported += 1

    # Notes not typed on a highlight become plain notes.
    loose = 0
    for c in mine:
        if c.kind == "note" and c.loc_start not in used_note_locs and c.text not in existing:
            existing.add(c.text)
            db.add(Note(book_id=book.id, kind="note", title="Kindle note", content=c.text, tags=["kindle"],
                        location={"page": c.page} if c.page else {}))
            loose += 1
    await db.commit()
    return {"imported": imported, "located": located, "duplicates": duplicates, "notes_attached": attached,
            "standalone_notes": loose}
