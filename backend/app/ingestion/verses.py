"""Chapter and verse structure for scriptures and other numbered texts (the Bible, the Quran...).

detect_verses() takes the chapters found by chapters.detect_chapters() (for a Bible these are
usually its books: "Genesis", "Exodus"...) and looks inside each one for verses, in either of the
two layouts real files use:

* reference markers: "1:1 In the beginning... 1:2 And the earth..." (also "1.1", "3:3-5"). Each
  marker carries its chapter, so chapters are found from the markers themselves.
* chapter headings and bare verse numbers: a short "Genesis 1" / "Chapter 1" / "Psalm 23"
  paragraph, then verse 1 (often unnumbered), then "2And the earth...", "[3] And God said...",
  "(4) And God saw...".

A number only counts as a verse marker when it continues the sequence (the next verse, or a few
further on when a translation leaves verses out), so ordinary numbers and cross references in the
text are left alone. Chapter headings that repeat the current chapter are page headers and are
dropped. When chapter numbering starts again at 1 inside one part of the file, a new section
begins (so Matthew 1 is never mixed up with Genesis 1).

The result is only used when it is reliable: enough verses, covering most of the book's text.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from app.ingestion.chapters import PARA_SEP, ChapterData
from app.ingestion.chunking import ChunkSpan, estimate_tokens, page_at

# ---------- book names ----------


@dataclass(frozen=True)
class BookName:
    name: str  # "1 Samuel"
    chapters: int | None  # chapters in the usual canon, a sanity check (None: varies by edition)
    abbreviations: tuple[str, ...] = ()
    numbered: bool = False  # "1 Samuel", "2 Samuel": the ordinal belongs to the name


def _b(name: str, chapters: int | None, *abbr: str) -> BookName:
    return BookName(name, chapters, abbr, numbered=name[0].isdigit())


BIBLE_BOOKS: tuple[BookName, ...] = (
    _b("Genesis", 50, "gen", "ge", "gn"), _b("Exodus", 40, "exod", "exo", "ex"),
    _b("Leviticus", 27, "lev", "le", "lv"), _b("Numbers", 36, "num", "nu", "nm", "nb"),
    _b("Deuteronomy", 34, "deut", "de", "dt"), _b("Joshua", 24, "josh", "jos", "jsh"),
    _b("Judges", 21, "judg", "jdg", "jg"), _b("Ruth", 4, "rth", "ru"),
    _b("1 Samuel", 31, "1 sam", "1 sa", "1 sm"), _b("2 Samuel", 24, "2 sam", "2 sa", "2 sm"),
    _b("1 Kings", 22, "1 kgs", "1 ki", "1 kin"), _b("2 Kings", 25, "2 kgs", "2 ki", "2 kin"),
    _b("1 Chronicles", 29, "1 chron", "1 chr", "1 ch"), _b("2 Chronicles", 36, "2 chron", "2 chr", "2 ch"),
    _b("Ezra", 10, "ezr", "ezra"), _b("Nehemiah", 13, "neh", "ne"), _b("Esther", 10, "esth", "est", "es"),
    _b("Job", 42, "jb"), _b("Psalms", 150, "psalm", "ps", "psa", "pss", "psm"),
    _b("Proverbs", 31, "prov", "pro", "prv", "pr"), _b("Ecclesiastes", 12, "eccles", "eccl", "ecc", "ec", "qoh"),
    _b("Song of Solomon", 8, "song of songs", "song", "sos", "canticles", "cant", "sg"),
    _b("Isaiah", 66, "isa", "is"), _b("Jeremiah", 52, "jer", "je", "jr"), _b("Lamentations", 5, "lam", "la"),
    _b("Ezekiel", 48, "ezek", "eze", "ezk"), _b("Daniel", 12, "dan", "da", "dn"), _b("Hosea", 14, "hos", "ho"),
    _b("Joel", 3, "jl"), _b("Amos", 9, "am"), _b("Obadiah", 1, "obad", "ob"), _b("Jonah", 4, "jon", "jnh"),
    _b("Micah", 7, "mic", "mc"), _b("Nahum", 3, "nah", "na"), _b("Habakkuk", 3, "hab", "hb"),
    _b("Zephaniah", 3, "zeph", "zep", "zp"), _b("Haggai", 2, "hag", "hg"), _b("Zechariah", 14, "zech", "zec", "zc"),
    _b("Malachi", 4, "mal", "ml"),
    _b("Matthew", 28, "matt", "mat", "mt"), _b("Mark", 16, "mrk", "mk", "mr"), _b("Luke", 24, "luk", "lk"),
    _b("John", 21, "joh", "jhn", "jn"), _b("Acts", 28, "act", "ac"), _b("Romans", 16, "rom", "ro", "rm"),
    _b("1 Corinthians", 16, "1 cor", "1 co"), _b("2 Corinthians", 13, "2 cor", "2 co"),
    _b("Galatians", 6, "gal", "ga"), _b("Ephesians", 6, "eph", "ephes"), _b("Philippians", 4, "phil", "php", "pp"),
    _b("Colossians", 4, "col", "co"), _b("1 Thessalonians", 5, "1 thess", "1 thes", "1 th"),
    _b("2 Thessalonians", 3, "2 thess", "2 thes", "2 th"), _b("1 Timothy", 6, "1 tim", "1 ti"),
    _b("2 Timothy", 4, "2 tim", "2 ti"), _b("Titus", 3, "tit", "ti"), _b("Philemon", 1, "philem", "phm", "pm"),
    _b("Hebrews", 13, "heb"), _b("James", 5, "jas", "jm"), _b("1 Peter", 5, "1 pet", "1 pe", "1 pt"),
    _b("2 Peter", 3, "2 pet", "2 pe", "2 pt"), _b("1 John", 5, "1 jn", "1 jo", "1 jhn"), _b("2 John", 1, "2 jn", "2 jo"),
    _b("3 John", 1, "3 jn", "3 jo"), _b("Jude", 1, "jud", "jd"),
    _b("Revelation", 22, "revelations", "apocalypse", "rev", "re", "rv"),
    # Apocrypha / deuterocanon: chapter counts differ between editions.
    _b("Tobit", None, "tob", "tb"), _b("Judith", None, "jdt", "jdth"),
    _b("Wisdom of Solomon", None, "wisdom", "wis", "ws"), _b("Sirach", None, "ecclesiasticus", "sir"),
    _b("Baruch", None, "bar"), _b("Letter of Jeremiah", None, "epistle of jeremiah", "let jer"),
    _b("Prayer of Azariah", None, "song of the three", "pr azar"), _b("Susanna", None, "sus"),
    _b("Bel and the Dragon", None, "bel"), _b("1 Maccabees", None, "1 macc", "1 mac", "1 ma"),
    _b("2 Maccabees", None, "2 macc", "2 mac", "2 ma"), _b("1 Esdras", None, "1 esd"), _b("2 Esdras", None, "2 esd"),
    _b("Prayer of Manasseh", None, "pr man", "manasseh"),
)
_BY_NAME = {b.name: b for b in BIBLE_BOOKS}

_ORDINALS = {"first": "1", "second": "2", "third": "3", "1st": "1", "2nd": "2", "3rd": "3", "i": "1", "ii": "2", "iii": "3"}
# Words that name a book on their own inside a long title ("The Song of Solomon", "Psalms").
_TITLE_WORDS = sorted(
    {b.name.split(" ", 1)[1] if b.numbered else b.name for b in BIBLE_BOOKS}
    | {"Song of Songs", "Ecclesiasticus", "Psalm", "Revelations", "Apocalypse"},
    key=len,
    reverse=True,
)
_TITLE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _TITLE_WORDS) + r")\b", re.I)
_ALIASES = {"song of songs": "Song of Solomon", "ecclesiasticus": "Sirach", "psalm": "Psalms",
            "revelations": "Revelation", "apocalypse": "Revelation"}


def book_name_from_title(title: str) -> str | None:
    """The usual short name of a Bible book from a heading: "The First Book of Moses: Called Genesis"
    -> "Genesis", "The First Epistle General of John" -> "1 John", "The Lamentations of Jeremiah" ->
    "Lamentations". None when the heading names no known book."""
    m = _TITLE_RE.search(title)
    if not m:
        return None
    word = m.group(1).lower()
    base = _ALIASES.get(word) or next(w for w in _TITLE_WORDS if w.lower() == word)
    numbered = [b for b in BIBLE_BOOKS if b.numbered and b.name.split(" ", 1)[1] == base]
    if not numbered:
        # Not a numbered book: in "The First Book of Moses: Called Genesis" the ordinal is Moses's.
        return base
    before = title[: m.start()].lower()
    ordinal = re.findall(r"\b(first|second|third|1st|2nd|3rd|iii|ii|i|[123])\b", before)
    if ordinal:
        num = _ORDINALS.get(ordinal[-1], ordinal[-1])
        if f"{num} {base}" in _BY_NAME:
            return f"{num} {base}"
    return base if base in _BY_NAME else numbered[0].name


# ---------- structures ----------


@dataclass
class Verse:
    number: int
    text: str  # clean text: no reference marker
    end: int | None = None  # last verse of a range ("3:3-5" -> number 3, end 5)
    page: int | None = None


@dataclass
class VerseChapter:
    number: int
    verses: list[Verse] = field(default_factory=list)
    title: str | None = None  # a psalm's superscription: text before verse 1
    title_page: int | None = None
    pages: list[int] = field(default_factory=list)  # pages the chapter spans (PDFs)

    def missing(self) -> list[int]:
        """Verse numbers skipped inside the chapter (some translations leave verses out)."""
        have = {n for v in self.verses for n in range(v.number, (v.end or v.number) + 1)}
        if not have:
            return []
        return [n for n in range(min(have), max(have) + 1) if n not in have]


@dataclass
class VerseSection:
    name: str  # "Genesis", or the heading as written when it isn't a known book
    heading: str  # the heading as it appears in the file
    chapters: list[VerseChapter] = field(default_factory=list)
    intro: str = ""  # text before the first chapter (the book's long title)
    named: str | None = None  # the book its headings name ("Genesis 1" -> Genesis)
    source_position: int = 0  # the ChapterData it came from

    @property
    def verse_count(self) -> int:
        return sum(len(c.verses) for c in self.chapters)


@dataclass
class VerseDetection:
    reliable: bool
    reason: str
    sections: list[VerseSection]
    other: list[ChapterData]  # parts without verses (preface, licence): kept as ordinary chapters
    coverage: float  # share of the book's text that is inside verses

    @property
    def chapter_count(self) -> int:
        return sum(len(s.chapters) for s in self.sections)

    @property
    def verse_count(self) -> int:
        return sum(s.verse_count for s in self.sections)

    def summary(self) -> str:
        n = len(self.sections)
        noun = "book" if n == 1 else "books"
        return f"Detected {n:,} {noun}, {self.chapter_count:,} chapters, {self.verse_count:,} verses"


# ---------- detection ----------

MIN_VERSES = 50  # fewer than this and it isn't a verse-structured book
MIN_COVERAGE = 0.6  # share of all text inside verses
MAX_SKIP = 3  # how far a verse number may jump (translations that omit verses)

# "1:1 ", "1.1 ", "3:3-5 ", "3:3–5 ", not inside a longer number ("10:30am", "1.1.2")
_CV = re.compile(r"(?<![\w:.,])(\d{1,3})[:.](\d{1,3})(?:\s?[-–]\s?(\d{1,3}))?(?=\s+[^\s\d])")
# A chapter heading paragraph: "Genesis 1", "Chapter 1", "CHAPTER 12", "Psalm 23", "Chapter Esther 10", "Surah 2"
_HEADING = re.compile(r"^(?:chapter\s+)?(?:[1-3]\s?)?[^\W\d_][\w .'’\-]{0,40}?\s+(\d{1,3})\.?$|^(?:chapter|psalm|surah|sura)\s+(\d{1,3})\b.{0,40}$", re.I)
# A bare verse number: "2And", "[2] And", "(2) And", "2 And"
_BARE = re.compile(r"(?:(?<=^)|(?<=[\s(\[“\"‘]))(?:\[(\d{1,3})(?:\s?[-–]\s?(\d{1,3}))?\]|\((\d{1,3})\)|(\d{1,3}))(\s?)(?=[A-Za-z“‘\"'(¶])")


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _pages(ch: ChapterData, start: int, end: int) -> list[int]:
    pm = ch.page_map
    if not pm:
        return []
    out = [p for o, p in pm if start <= o < end]
    before = [p for o, p in pm if o <= start]
    if before and (not out or out[0] != before[-1]):
        out.insert(0, before[-1])
    return out


def _by_markers(ch: ChapterData) -> list[VerseSection]:
    """Layout 1: "1:1 In the beginning..." markers carry chapter and verse."""
    text = ch.text
    # Headings between verses: a book's name ("Psalms", "The Gospel According to Saint John") starts a
    # new book; a chapter heading ("Chapter 2") only ends the verse before it.
    cuts: list[int] = []
    books: dict[int, str] = {}
    for off, para in _paragraphs(text):
        line = para.strip()
        if not line or len(line) > 80 or _CV.search(line):
            continue
        if _HEADING.match(line):
            cuts.append(off)
        elif not re.search(r"[.;,:!?]$", line) and book_name_from_title(line):
            cuts.append(off)
            books[off] = line
    book_offsets = sorted(books)

    accepted: list[tuple[re.Match, int, int, int | None]] = []
    breaks: dict[int, str] = {}  # accepted index -> the heading of the book that starts there
    c = v = 0
    for m in _CV.finditer(text):
        c2, v2 = int(m.group(1)), int(m.group(2))
        end = int(m.group(3)) if m.group(3) else None
        if accepted:
            k = bisect.bisect_right(book_offsets, m.start()) - 1
            if k >= 0 and book_offsets[k] > accepted[-1][0].start():
                if v2 <= MAX_SKIP + 1:  # a new book: its numbering starts afresh
                    breaks[len(accepted)] = books[book_offsets[k]]
                    accepted.append((m, c2, v2, end if end is not None and v2 < end <= v2 + 30 else None))
                    c, v = c2, accepted[-1][3] or v2
                continue
        if not accepted:
            ok = v2 <= MAX_SKIP + 1
        elif c2 == c:
            ok = v < v2 <= v + MAX_SKIP + 1
        elif c2 in (c + 1, c + 2):
            ok = v2 <= MAX_SKIP + 1
        elif c2 > c and v2 <= MAX_SKIP + 1:
            # further ahead only when a chapter heading stands between ("Matthew 17" after Matthew 1)
            k = bisect.bisect_right(cuts, m.start()) - 1
            ok = k >= 0 and cuts[k] > accepted[-1][0].start()
        else:
            ok = c2 == 1 and v2 <= MAX_SKIP + 1 and c > 1  # numbering starts again: a new book
        if ok:
            if end is not None and not v2 < end <= v2 + 30:
                end = None
            accepted.append((m, c2, v2, end))
            c, v = c2, end or v2
    if not accepted:
        return []

    sections: list[VerseSection] = [VerseSection(name="", heading=ch.title, intro=_tidy(text[: accepted[0][0].start()]), source_position=ch.position)]
    first_books = [o for o in book_offsets if o < accepted[0][0].start()]
    if first_books:
        sections[0].named = book_name_from_title(books[first_books[-1]])
    chapter: VerseChapter | None = None
    for i, (m, c2, v2, end) in enumerate(accepted):
        nxt = accepted[i + 1][0].start() if i + 1 < len(accepted) else len(text)
        k = bisect.bisect_right(cuts, m.start())
        if k < len(cuts) and cuts[k] < nxt:
            nxt = cuts[k]  # a heading ends the verse
        body = _tidy(text[m.end() : nxt])
        if i in breaks:
            sections.append(VerseSection(name="", heading=breaks[i], source_position=ch.position))
            chapter = None
        elif chapter is not None and c2 < chapter.number:
            sections.append(VerseSection(name="", heading=f"{ch.title} (part {len(sections) + 1})", source_position=ch.position))
            chapter = None
        if chapter is None or c2 != chapter.number:
            chapter = VerseChapter(number=c2, pages=_pages(ch, m.start(), nxt))
            sections[-1].chapters.append(chapter)
            # Text between the chapter's heading and its first verse is its title (a psalm's superscription).
            k = bisect.bisect_right(cuts, m.start()) - 1
            prev = accepted[i - 1][0].start() if i else -1
            if i and k >= 0 and cuts[k] > prev and v2 == 1:
                after_heading = text[cuts[k] : m.start()].split(PARA_SEP, 1)
                title = _tidy(after_heading[1]) if len(after_heading) > 1 else ""
                if title and not _is_book_heading(title):
                    chapter.title, chapter.title_page = title, page_at(ch.page_map, cuts[k])
        elif ch.page_map:
            chapter.pages = sorted(set(chapter.pages) | set(_pages(ch, m.start(), nxt)))
        if body:
            chapter.verses.append(Verse(number=v2, text=body, end=end, page=page_at(ch.page_map, m.start())))
    return sections


_INLINE_HEADING = re.compile(r"^((?:chapter|psalm|surah|sura)\s+\d{1,3})\s+(?=\S)", re.I)


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """[(offset, paragraph)]. "Chapter 1 There dwelt a man..." is split into its heading and its text."""
    out, at = [], 0
    for para in text.split(PARA_SEP):
        m = _INLINE_HEADING.match(para)
        if m and len(para) > 50:
            out += [(at, m.group(1)), (at + m.end(), para[m.end() :])]
        else:
            out.append((at, para))
        at += len(para) + len(PARA_SEP)
    return out


_ORDINAL_FIRST = re.compile(r"^\s*(?:chapter\s+)?(?:[123]|first|second|third|i{1,3})\b", re.I)


def _other_book(heading: str, named: str, book: str) -> bool:
    """Whether a heading names a different book from the current one. "Chapter Samuel 2" inside 2 Samuel
    doesn't: without its own number, a heading only changes the book when the name itself changes."""
    if named == book:
        return False
    if _ORDINAL_FIRST.match(heading):
        return True
    def base(name: str) -> str:
        return name.split(" ", 1)[1] if name[0].isdigit() else name
    return base(named) != base(book)


def _is_book_heading(para: str) -> bool:
    """A paragraph that is just a book's name ("Psalms", "The Gospel According to Saint John")."""
    line = para.strip()
    return 0 < len(line) <= 80 and not re.search(r"[.;,:!?\d]$", line) and book_name_from_title(line) is not None \
        and len(line.split()) <= 10


def _split_bare(body: str) -> tuple[str, list[tuple[int, int | None, int, str]]]:
    """Text before the first verse marker, and [(verse number, last verse of a range, offset, text)]."""
    marks: list[tuple[int, int, int, int | None]] = []  # (start, end, number, last verse of a range)
    v = 0
    for m in _BARE.finditer(body):
        n = int(m.group(1) or m.group(3) or m.group(4))
        last = int(m.group(2)) if m.group(2) and n < int(m.group(2)) <= n + 30 else None
        spaced = m.group(4) is not None and m.group(5) == " "
        if spaced:
            # "2 And" is a verse only at the start of a paragraph or after punctuation ("...face. 2 And")
            before = body[max(0, m.start() - 2) : m.start()]
            if m.start() > 0 and not re.search(r"(?:^|[.;:!?,)\]”’\"'\n])\s*$", before):
                continue
        if (not marks and 1 <= n <= MAX_SKIP + 30) or (marks and v < n <= v + MAX_SKIP):
            marks.append((m.start(), m.end(), n, last))
            v = last or n
    if not marks:
        return body, []
    lead = body[: marks[0][0]]
    verses = [(n, last, e, body[e : marks[i + 1][0] if i + 1 < len(marks) else len(body)]) for i, (_, e, n, last) in enumerate(marks)]
    return lead, verses


def _by_headings(ch: ChapterData) -> list[VerseSection]:
    """Layout 2: "Genesis 1" headings, then verse 1 (often unnumbered), then "2And the earth..."."""
    paras = _paragraphs(ch.text)
    heads: list[tuple[int, int, int, str | None]] = []  # (para index, chapter number, char offset, new book)
    drop: set[int] = set()  # repeated headings (page headers)
    c = 0
    book: str | None = None  # the book named by the headings ("Genesis 2" -> Genesis)
    for i, (off, p) in enumerate(paras):
        if len(p) > 50:
            continue
        m = _HEADING.match(p.strip())
        if not m:
            continue
        n = int(m.group(1) or m.group(2))
        named = book_name_from_title(p.strip())
        if heads and named and book and _other_book(p, named, book):
            heads.append((i, n, off, named))  # another book: its numbering starts afresh
            c, book = n, named
        elif heads and n == c:
            drop.add(i)
        elif not heads or n in (c + 1, c + 2) or (n == 1 and c > 1) or (n > c and named and named == book):
            heads.append((i, n, off, None))
            c, book = n, named or book
    if len(heads) < 1:
        return []

    sections = [VerseSection(name="", heading=ch.title, source_position=ch.position,
                             named=book_name_from_title(paras[heads[0][0]][1].strip()))]
    intro = [p for _, p in paras[: heads[0][0]]]
    sections[0].intro = _tidy(" ".join(intro))
    for k, (i, n, off, new_book) in enumerate(heads):
        stop = heads[k + 1][0] if k + 1 < len(heads) else len(paras)
        # (the book's own name repeated inside a chapter is a page header too)
        kept = [(o, p) for j, (o, p) in enumerate(paras[i + 1 : stop], start=i + 1)
                if j not in drop and p.strip() != ch.title.strip() and not _is_book_heading(p)]
        body = "\n".join(p for _, p in kept)
        starts, at = [], 0  # where each kept paragraph starts in `body`, for page numbers
        for _, p in kept:
            starts.append(at)
            at += len(p) + 1

        def page(at: int, kept=kept, starts=starts, off=off) -> int | None:
            if not kept:
                return page_at(ch.page_map, off)
            k = max(0, bisect.bisect_right(starts, at) - 1)
            return page_at(ch.page_map, kept[k][0] + at - starts[k])

        end_off = paras[stop][0] if stop < len(paras) else len(ch.text)
        if new_book and sections[-1].chapters:
            sections.append(VerseSection(name="", heading=new_book, source_position=ch.position))
        elif sections[-1].chapters and n < sections[-1].chapters[-1].number:
            sections.append(VerseSection(name="", heading=f"{ch.title} (part {len(sections) + 1})", source_position=ch.position))
        chapter = VerseChapter(number=n, pages=_pages(ch, off, end_off))
        lead, numbered = _split_bare(body)
        lead = _tidy(lead)
        first = numbered[0][0] if numbered else None
        if first == 1:
            chapter.title = lead or None  # text before an explicit verse 1: a superscription
            chapter.title_page = page(0)
        elif lead:
            chapter.verses.append(Verse(number=(first - 1) if first and first > 1 else 1, text=lead, page=page(0)))
        for num, last, at, t in numbered:
            t = _tidy(t)
            if t:
                chapter.verses.append(Verse(number=num, text=t, end=last, page=page(at)))
        sections[-1].chapters.append(chapter)
    return sections


def _covered(sections: list[VerseSection]) -> int:
    return sum(len(v.text) for s in sections for c in s.chapters for v in c.verses)


def detect_verses(chapters: list[ChapterData]) -> VerseDetection:
    sections: list[VerseSection] = []
    other: list[ChapterData] = []
    total = sum(len(ch.text) for ch in chapters) or 1
    for ch in chapters:
        a, b = _by_markers(ch), _by_headings(ch)
        found = max((a, b), key=lambda f: (sum(x.verse_count for x in f), _covered(f)))
        # A part with only a handful of verses (an index of references, a preface quoting one) stays as it is.
        if sum(s.verse_count for s in found) < 3 or _covered(found) < 0.5 * len(ch.text):
            other.append(ch)
            continue
        sections.extend(found)

    used: set[str] = set()
    for s in sections:
        name = book_name_from_title(s.heading) or s.named or book_name_from_title(s.intro[-200:]) or s.heading
        s.name = name if name not in used else s.heading
        used.add(s.name)

    covered = _covered(sections)
    coverage = covered / total
    verses = sum(s.verse_count for s in sections)
    if verses < MIN_VERSES:
        return VerseDetection(False, f"Only {verses} verses found", sections, other, coverage)
    if coverage < MIN_COVERAGE:
        return VerseDetection(False, f"Verses cover only {coverage:.0%} of the text", sections, other, coverage)
    return VerseDetection(True, "", sections, other, coverage)


# ---------- chapters and passages for indexing ----------


@dataclass
class VerseSpan:
    """A verse's place in its chapter's text (what the verses table stores)."""

    number: int  # 0 for a chapter title
    end: int | None
    kind: str  # verse | title
    start: int
    stop: int
    text: str
    page: int | None


def chapter_title(section: str, number: int) -> str:
    return f"Psalm {number}" if section == "Psalms" else f"{section} {number}"


def verse_chapters(detection: VerseDetection, source: list[ChapterData]) -> list[ChapterData]:
    """The book as one chapter per scripture chapter ("Genesis 1"), with the parts that have no verses
    (preface, licence) kept as they were, all in reading order. Each verse is its own paragraph and
    the text carries no reference markers."""
    by_source: dict[int, list[VerseSection]] = {}
    for sec in detection.sections:
        by_source.setdefault(sec.source_position, []).append(sec)
    out: list[ChapterData] = []
    for ch in source:
        if ch.position not in by_source:
            out.append(ChapterData(position=0, title=ch.title, text=ch.text, page_map=ch.page_map))
            continue
        for section in by_source[ch.position]:
            for vc in section.chapters:
                spans: list[VerseSpan] = []
                parts: list[str] = []
                at = 0
                items = ([(0, None, "title", vc.title, vc.title_page)] if vc.title else []) + [
                    (v.number, v.end, "verse", v.text, v.page) for v in vc.verses
                ]
                for number, end, kind, text, page in items:
                    spans.append(VerseSpan(number, end, kind, at, at + len(text), text, page))
                    parts.append(text)
                    at += len(text) + len(PARA_SEP)
                page_map: list[list[int]] = []
                for sp in spans:
                    if sp.page is not None and (not page_map or page_map[-1][1] != sp.page):
                        page_map.append([sp.start, sp.page])
                out.append(ChapterData(
                    position=0, title=chapter_title(section.name, vc.number), text=PARA_SEP.join(parts),
                    page_map=page_map, section=section.name, number=vc.number, verses=spans,
                ))
    for n, ch in enumerate(out, start=1):
        ch.position = n
    return out


def chunk_verses(
    text: str, spans: list[VerseSpan], target_tokens: int = 200, max_tokens: int = 350
) -> list[tuple[ChunkSpan, int | None, int | None]]:
    """Passages of a few whole verses (never a verse cut in half), each with the verses it covers.
    Consecutive passages share one verse, so a thought that runs across the break is still found."""
    out: list[tuple[ChunkSpan, int | None, int | None]] = []
    i, n = 0, len(spans)
    while i < n:
        j, tokens = i, 0
        while j < n:
            t = estimate_tokens(spans[j].text)
            if tokens and tokens + t > max_tokens:
                break
            tokens += t
            j += 1
            if tokens >= target_tokens:
                break
        group = spans[i:j]
        s, e = group[0].start, group[-1].stop
        numbers = [v for sp in group if sp.kind == "verse" for v in (sp.number, sp.end or sp.number)]
        out.append((ChunkSpan(s, e, text[s:e], estimate_tokens(text[s:e])),
                    min(numbers) if numbers else None, max(numbers) if numbers else None))
        if j >= n:
            break
        i = j - 1 if j - i > 2 else j  # overlap by one verse when the passage has several
    return out


def verse_label(title: str, start: int | None, end: int | None) -> str:
    """("Genesis 1", 3, 5) -> "Genesis 1:3–5"."""
    if start is None:
        return title
    return f"{title}:{start}" + (f"–{end}" if end and end != start else "")


# ---------- references: "John 3:16", "Gen 1:3", "1 Cor 13:4-7", "Ps 23", "3:16" ----------


@dataclass
class Reference:
    book: str | None  # as typed ("gen", "1 cor"); None for "3:16" (the book on screen)
    chapter: int | None  # None for a book alone ("Jude")
    verse: int | None = None
    verse_end: int | None = None


_REF = re.compile(
    r"^(?P<book>.*?)\s*(?P<ch>\d{1,3})(?:\s*[:.,]\s*(?P<v>\d{1,3})(?:\s*[-–—]\s*(?P<ve>\d{1,3}))?|\s+(?P<v2>\d{1,3}))?$"
)
_LEADING_ORDINAL = re.compile(r"^(?:(1st|first|i)|(2nd|second|ii)|(3rd|third|iii))\s+(?=[a-z])")


def _norm_book(text: str) -> str:
    """ "1st John", "First John", "I John", "1John", "1 jn." -> "1 john", "1 jn"."""
    t = re.sub(r"[.]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    m = _LEADING_ORDINAL.match(t)
    if m:
        num = "1" if m.group(1) else "2" if m.group(2) else "3"
        t = f"{num} {t[m.end():]}"
    return re.sub(r"^([123])\s*(?=[a-z])", r"\1 ", t)


def parse_reference(text: str) -> Reference | None:
    """A typed reference, or None if it doesn't look like one. The book name is kept as typed; see
    resolve_book() for matching it to the book's own sections."""
    t = re.sub(r"\s+", " ", text.strip())
    if not t or len(t) > 80:
        return None
    m = _REF.match(t)
    if m:
        book = m.group("book").strip(" ,")
        verse = m.group("v") or m.group("v2")
        if book and not re.search(r"[a-zA-Z]", book):
            return None  # "1 2 3"
        if not book and not m.group("v"):
            return None  # a bare number is not a reference
        end = int(m.group("ve")) if m.group("ve") else None
        ref = Reference(book or None, int(m.group("ch")), int(verse) if verse else None, end)
        if ref.verse_end is not None and ref.verse is not None and ref.verse_end <= ref.verse:
            ref.verse_end = None
        return ref
    if re.fullmatch(r"[123]?\s?[a-zA-Z][a-zA-Z .']{1,40}", t):
        return Reference(t, None)  # a book alone: "Jude", "Psalms"
    return None


_LOOKUP: dict[str, str] = {}
for _book in BIBLE_BOOKS:
    _LOOKUP[_book.name.lower()] = _book.name
    for _abbr in _book.abbreviations:
        _LOOKUP.setdefault(_abbr, _book.name)
for _alias, _name in _ALIASES.items():
    _LOOKUP.setdefault(_alias, _name)
_LOOKUP.update({"psalm": "Psalms", "song of songs": "Song of Solomon", "canticle of canticles": "Song of Solomon"})


def resolve_book(typed: str, sections: list[str]) -> str | None:
    """Which of this book's sections a typed name means: its own name ("Esther Additions"), a Bible
    book's name or abbreviation ("Gen", "1 Cor", "Psalm"), or the start of a name ("Deut", "Matt")."""
    t = _norm_book(typed)
    if not t:
        return None
    own = {_norm_book(s): s for s in sections}
    if t in own:
        return own[t]
    canonical = _LOOKUP.get(t) or _LOOKUP.get(t.replace(" ", ""))
    if canonical and canonical in sections:
        return canonical
    starts = [s for n, s in own.items() if n.startswith(t)] or [s for n, s in own.items() if n.replace(" ", "").startswith(t.replace(" ", ""))]
    if len(starts) == 1:
        return starts[0]
    if starts:  # "Jo" -> Job, Joel, John, Jonah, Joshua: the shortest name ("Job") is a guess, so don't
        exact_word = [s for s in starts if _norm_book(s).split(" ")[-1] == t.split(" ")[-1]]
        return exact_word[0] if len(exact_word) == 1 else None
    return None
