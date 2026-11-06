"""Chapter-and-verse structure: detection, references and the text read aloud (no database).

The samples in tests/data are King James Version chapters (public domain) in the two layouts real
files use: "1:1 In the beginning..." markers, and "Genesis 1" headings with bare verse numbers.
Both hold Genesis 1-2, Psalms 3 and 23 (with their titles), Matthew 1 and 17 (17:21 left out, as
in many modern translations) and John 3 (verses 3-5 printed as one range): four books, two of
them starting again at chapter 1.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ingestion.chapters import ChapterData, detect_chapters
from app.ingestion.cleaning import clean_document
from app.ingestion.parsers import parse_file
from app.ingestion.verses import (
    book_name_from_title,
    chunk_verses,
    detect_verses,
    parse_reference,
    resolve_book,
    verse_chapters,
    verse_label,
)
from app.tts.verses import chapter_announcement, speech_items, spoken_book, verse_announcement, without_markers

DATA = Path(__file__).parent / "data"
SAMPLES = ["kjv_sample.txt", "kjv_sample_headings.txt"]
# anything that could be read out as "one colon four" / "one point four" / "bracket four"
MARKER = re.compile(r"\b\d{1,3}\s*[:.]\s*\d{1,3}\b|\[\d|\(\d{1,3}\)|^\d")


def _detect(name: str):
    doc = parse_file(DATA / name, lambda *_: None)
    clean_document(doc)
    chapters = detect_chapters(doc)
    return detect_verses(chapters), chapters


def _chapter(detection, book: str, number: int):
    return next(c for s in detection.sections if s.name == book for c in s.chapters if c.number == number)


# ---------- detection on realistic samples ----------


@pytest.mark.parametrize("sample", SAMPLES)
def test_sample_structure(sample):
    d, _ = _detect(sample)
    assert d.reliable, d.reason
    assert d.summary() == "Detected 4 books, 7 chapters, 155 verses"
    assert [s.name for s in d.sections] == ["Genesis", "Psalms", "Matthew", "John"]
    assert [(s.name, [c.number for c in s.chapters]) for s in d.sections] == [
        ("Genesis", [1, 2]), ("Psalms", [3, 23]), ("Matthew", [1, 17]), ("John", [3]),
    ]
    assert len(_chapter(d, "Genesis", 1).verses) == 31
    assert _chapter(d, "Genesis", 1).verses[0].text == "In the beginning God created the heaven and the earth."


@pytest.mark.parametrize("sample", SAMPLES)
def test_repeated_chapter_numbers_stay_in_their_own_book(sample):
    d, _ = _detect(sample)
    genesis1, matthew1 = _chapter(d, "Genesis", 1), _chapter(d, "Matthew", 1)
    assert genesis1.verses[0].text.startswith("In the beginning")
    assert matthew1.verses[0].text.startswith("The book of the generation of Jesus Christ")


@pytest.mark.parametrize("sample", SAMPLES)
def test_ranges_missing_verses_and_titles(sample):
    d, _ = _detect(sample)
    john3 = _chapter(d, "John", 3)
    assert [(v.number, v.end) for v in john3.verses[:4]] == [(1, None), (2, None), (3, 5), (6, None)]
    assert john3.missing() == []  # 4 and 5 are inside the range
    matthew17 = _chapter(d, "Matthew", 17)
    assert matthew17.missing() == [21]
    assert [v.number for v in matthew17.verses][19:22] == [20, 22, 23]
    assert _chapter(d, "Psalms", 3).title == "A Psalm of David, when he fled from Absalom his son."
    assert _chapter(d, "Psalms", 23).verses[0].text == "The LORD is my shepherd; I shall not want."


@pytest.mark.parametrize("sample", SAMPLES)
def test_no_reference_marker_is_left_in_verse_text(sample):
    d, _ = _detect(sample)
    texts = [v.text for s in d.sections for c in s.chapters for v in c.verses]
    assert len(texts) == 155  # verse rows (the range 3-5 is one of them)
    assert not [t for t in texts if MARKER.search(t)]


@pytest.mark.parametrize("sample", SAMPLES)
def test_chapters_and_passages_for_indexing(sample):
    d, source = _detect(sample)
    chapters = verse_chapters(d, source)
    assert [c.title for c in chapters] == ["Genesis 1", "Genesis 2", "Psalm 3", "Psalm 23", "Matthew 1", "Matthew 17", "John 3"]
    for ch in chapters:
        for v in ch.verses:  # every verse is an exact slice of its chapter's text
            assert ch.text[v.start : v.stop] == v.text
        passages = chunk_verses(ch.text, ch.verses)
        covered = {n for _, a, b in passages if a is not None for n in range(a, b + 1)}
        numbers = {n for v in ch.verses if v.kind == "verse" for n in range(v.number, (v.end or v.number) + 1)}
        assert numbers <= covered  # every verse is in a passage (a passage "20-22" also spans a left-out 21)
        for span, a, b in passages:  # passages hold whole verses only
            assert any(v.start == span.char_start for v in ch.verses)
            assert any(v.stop == span.char_end for v in ch.verses)
    psalm3 = chapters[2]
    assert psalm3.verses[0].kind == "title" and psalm3.text.startswith("A Psalm of David")


def _chapter_data(title: str, text: str, position: int = 1) -> ChapterData:
    return ChapterData(position=position, title=title, text=text)


def test_page_headers_and_inline_chapter_headings():
    """PDF layout: a repeated "Jude 1" page header, "Chapter 1 Jude, the servant..." on one line."""
    body = (
        "Jude\n\nThe General Epistle of\n\nJude\n\nJude 1\n\n"
        "Chapter 1 Jude, the servant of Jesus Christ, and brother of James: 2Mercy unto you, and peace, and love, be multiplied. "
        "3Beloved, when I gave all diligence to write unto you of the common salvation, it was needful for me to write unto you.\n\n"
        "Jude 1\n\n"
        "4For there are certain men crept in unawares, who were before of old ordained to this condemnation. "
        "5I will therefore put you in remembrance, though ye once knew this."
    )
    d = detect_verses([_chapter_data("Jude", body)])
    [section] = d.sections
    [chapter] = section.chapters
    assert section.name == "Jude"
    assert [v.number for v in chapter.verses] == [1, 2, 3, 4, 5]
    assert chapter.verses[0].text.startswith("Jude, the servant")  # not "Chapter 1 Jude..."
    assert not any("Jude 1" in v.text for v in chapter.verses)  # the page header is gone


def test_numbered_books_keep_their_number():
    """ "Chapter Samuel 2" (no "2" in front) inside 2 Samuel must not start another book."""
    verses = " ".join(f"{n}Verse {n} of this chapter goes here and says something." for n in range(2, 8))
    body = "".join(f"2 Samuel {c}\n\nChapter Samuel {c}\n\nThe first verse. {verses}\n\n" for c in (1, 2, 3))
    d = detect_verses([_chapter_data("2 Samuel", body)])
    assert [(s.name, [c.number for c in s.chapters]) for s in d.sections] == [("2 Samuel", [1, 2, 3])]


def test_ordinary_books_are_not_mistaken_for_scripture():
    text = "\n\n".join(
        f"At 10:{n:02d} the train left. She counted 3 bags, 2 boxes and 1 umbrella, then read chapter {n} again." for n in range(10, 60)
    )
    d = detect_verses([_chapter_data("Chapter 1", text)])
    assert not d.reliable


@pytest.mark.parametrize("title, name", [
    ("The First Book of Moses: Called Genesis", "Genesis"),
    ("The First Book of Samuel", "1 Samuel"),
    ("The Second Book of the Kings", "2 Kings"),
    ("The Gospel According to Saint John", "John"),
    ("The First Epistle General of John", "1 John"),
    ("The Lamentations of Jeremiah", "Lamentations"),
    ("The Revelation of Saint John the Divine", "Revelation"),
    ("The Song of Solomon", "Song of Solomon"),
    ("Psalm 23", "Psalms"),
    ("The Lighthouse Keeper", None),
])
def test_book_names_from_headings(title, name):
    assert book_name_from_title(title) == name


# ---------- references ----------

BOOKS = ["Genesis", "Exodus", "Psalms", "Matthew", "John", "1 John", "1 Corinthians", "Philippians", "Philemon",
         "Job", "Joel", "Jonah", "Joshua", "Song of Solomon", "Esther Additions"]


@pytest.mark.parametrize("text, book, chapter, verse, end, resolved", [
    ("John 3:16", "John", 3, 16, None, "John"),
    ("Gen 1:3", "Gen", 1, 3, None, "Genesis"),
    ("3:16", None, 3, 16, None, None),
    ("1 Cor 13:4-7", "1 Cor", 13, 4, 7, "1 Corinthians"),
    ("First John 4:8", "First John", 4, 8, None, "1 John"),
    ("1Jn 4:8", "1Jn", 4, 8, None, "1 John"),
    ("Ps 23", "Ps", 23, None, None, "Psalms"),
    ("Psalm 23:1", "Psalm", 23, 1, None, "Psalms"),
    ("jn 3 16", "jn", 3, 16, None, "John"),
    ("Song of Songs 2:1", "Song of Songs", 2, 1, None, "Song of Solomon"),
    ("Phil 4:13", "Phil", 4, 13, None, "Philippians"),
    ("Philem 1", "Philem", 1, None, None, "Philemon"),
    ("Esther Additions 11:2", "Esther Additions", 11, 2, None, "Esther Additions"),
    ("Jo 1:1", "Jo", 1, 1, None, None),  # Job, Joel, John, Jonah, Joshua: ambiguous
])
def test_references(text, book, chapter, verse, end, resolved):
    ref = parse_reference(text)
    assert (ref.book, ref.chapter, ref.verse, ref.verse_end) == (book, chapter, verse, end)
    assert (resolve_book(ref.book, BOOKS) if ref.book else None) == resolved


@pytest.mark.parametrize("text", ["12", "1 2 3", "", "x" * 120])
def test_not_references(text):
    assert parse_reference(text) is None


def test_verse_labels():
    assert verse_label("Genesis 1", 3, 5) == "Genesis 1:3–5"
    assert verse_label("John 3", 16, 16) == "John 3:16"
    assert verse_label("Preface", None, None) == "Preface"


# ---------- what is read aloud ----------


def _rows(chapter):
    """Verse rows as the database stores them, from a ChapterData built by verse_chapters()."""
    return [SimpleNamespace(number=v.number, end=v.end, kind=v.kind, char_start=v.start, char_end=v.stop, text=v.text)
            for v in chapter.verses]


@pytest.mark.parametrize("sample", SAMPLES)
def test_speech_never_contains_reference_markers(sample):
    d, source = _detect(sample)
    for ch in verse_chapters(d, source):
        items = speech_items(ch.section, ch.number, _rows(ch))
        spoken = [i["text"] for i in items if i["kind"] in ("text", "title")]
        assert spoken and not [t for t in spoken if MARKER.search(t)], ch.title
        # and the announcements are words, never "1:4"
        assert not [i["text"] for i in items if re.search(r"\d\s*[:.]\s*\d", i["text"])]


@pytest.mark.parametrize("sample", SAMPLES)
def test_chapter_is_announced_once_at_the_start(sample):
    d, source = _detect(sample)
    for ch in verse_chapters(d, source):
        items = speech_items(ch.section, ch.number, _rows(ch))
        kinds = [i["kind"] for i in items]
        assert kinds[0] == "chapter" and kinds.count("chapter") == 1, ch.title


def test_speech_order_title_ranges_and_missing_verses():
    d, source = _detect("kjv_sample.txt")
    chapters = {c.title: c for c in verse_chapters(d, source)}
    psalm = speech_items("Psalms", 23, _rows(chapters["Psalm 23"]))
    assert [(i["kind"], i["text"]) for i in psalm[:4]] == [
        ("chapter", "Psalm 23."), ("title", "A Psalm of David."), ("verse-number", "Verse 1."),
        ("text", "The LORD is my shepherd; I shall not want."),
    ]
    john = [i["text"] for i in speech_items("John", 3, _rows(chapters["John 3"]))]
    assert john[0] == "John, chapter 3."
    assert "Verses 3 to 5." in john and "Verse 4." not in john
    matthew = [i["text"] for i in speech_items("Matthew", 17, _rows(chapters["Matthew 17"]))]
    assert "Verse 20." in matthew and "Verse 22." in matthew and "Verse 21." not in matthew  # skipped silently
    # every item of a verse covers the whole verse, so the reader highlights the verse being read
    v16 = [i for i in speech_items("John", 3, _rows(chapters["John 3"])) if i["verse"] == 16]
    assert len({(i["start"], i["end"]) for i in v16}) == 1


def test_announcements_and_marker_stripping():
    assert chapter_announcement("Genesis", 1) == "Genesis, chapter 1."
    assert chapter_announcement("1 Samuel", 3) == "First Samuel, chapter 3."
    assert chapter_announcement("Psalms", 23) == "Psalm 23."
    assert spoken_book("2 Kings") == "Second Kings"
    assert verse_announcement(1) == "Verse 1."
    assert verse_announcement(3, 5) == "Verses 3 to 5."
    for raw in ["1:4 And God saw", "1.4 And God saw", "4And God saw", "[4] And God saw", "(4) And God saw"]:
        assert without_markers(raw) == "And God saw"
    assert without_markers("as it is written in 3:3-5, so") == "as it is written in, so"
    assert without_markers("He was 30 years old") == "He was 30 years old"
