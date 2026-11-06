"""Reading a chapter of a book with verses aloud (the Bible, the Quran...).

The spoken text is built from the stored structure (chapter number, verse number, clean verse
text), never from the raw text of the file, so a reference marker such as "1:4" can't be read out
as "one colon four". In reading order:

    "Genesis, chapter 1."                       once, when the chapter starts
    "A Psalm of David."                         the chapter's title (a psalm's superscription), if any
    "Verse 1."  "In the beginning God..."       each verse: its number, then its text
    "Verses 3 to 5."  "..."                     a range printed as one verse

Each announcement is an item of its own, so its audio is cached once and reused everywhere
("Verse 1." in every chapter), and the player can leave announcements out (the listener's
settings). Every item of a verse covers the whole verse (start/end), so the reader highlights
the verse being read.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from app.tts.text import split_sentences

_ORDINALS = {"1": "First", "2": "Second", "3": "Third"}

# Reference markers that must never be spoken: "1:4", "1.4", "3:3-5", "[4]", "[3-5]", "(4)", and a
# number glued to the start of a verse ("4And God saw...").
_MARKER = re.compile(
    r"(?<![\w.,])(?:\[\d{1,3}(?:\s?[-–]\s?\d{1,3})?\]|\(\d{1,3}\)|\d{1,3}[:.]\d{1,3}(?:\s?[-–]\s?\d{1,3})?)(?![\w])"
)
_LEADING_NUMBER = re.compile(r"^\s*\d{1,3}(?=[A-Za-z“‘\"'(])")


class VerseRow(Protocol):
    number: int
    end: int | None
    kind: str  # verse | title
    char_start: int
    char_end: int
    text: str


def spoken_book(name: str) -> str:
    """ "1 Samuel" -> "First Samuel" (voices read "1 Samuel" as "one Samuel")."""
    m = re.match(r"^([123]) (.+)$", name)
    return f"{_ORDINALS[m.group(1)]} {m.group(2)}" if m else name


def chapter_announcement(section: str, number: int) -> str:
    if section == "Psalms":
        return f"Psalm {number}."
    return f"{spoken_book(section)}, chapter {number}."


def verse_announcement(number: int, end: int | None = None) -> str:
    return f"Verses {number} to {end}." if end and end != number else f"Verse {number}."


def without_markers(text: str) -> str:
    """Verse text as spoken: any reference marker left in it removed (stored verses have none, but
    nothing that looks like one may ever reach the voice)."""
    t = _LEADING_NUMBER.sub("", text)
    t = _MARKER.sub("", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)  # "written in 3:3-5, so" -> "written in, so"
    return re.sub(r"\s{2,}", " ", t).strip()


def speech_items(section: str, number: int, verses: Sequence[VerseRow]) -> list[dict]:
    """The chapter as items to read aloud, in order. kind: chapter | title | verse-number | text.
    start/end are offsets into the chapter text (the whole verse); p is the verse's paragraph."""
    if not verses:
        return []
    first = verses[0].char_start
    items = [{"kind": "chapter", "text": chapter_announcement(section, number), "start": first, "end": first, "p": first,
              "verse": None, "verse_end": None}]
    for v in verses:
        span = {"start": v.char_start, "end": v.char_end, "p": v.char_start}
        if v.kind == "title":
            items += [{"kind": "title", "text": s.text, **span, "verse": None, "verse_end": None}
                      for s in split_sentences(without_markers(v.text))]
            continue
        sentences = [s.text for s in split_sentences(without_markers(v.text))]
        if not sentences:
            continue  # nothing to say: skip the verse, number and all
        items.append({"kind": "verse-number", "text": verse_announcement(v.number, v.end), **span,
                      "verse": v.number, "verse_end": v.end})
        items += [{"kind": "text", "text": s, **span, "verse": v.number, "verse_end": v.end} for s in sentences]
    return items
