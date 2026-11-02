"""Chapter/section detection.

Priority: explicit headings from the parser (PDF outline, EPUB TOC, DOCX/Markdown
headings) -> regex heading detection on short paragraphs -> fixed-size sections.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.parsers.base import ParsedDocument

PARA_SEP = "\n\n"

_NUM_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|first|second|third|fourth|fifth|"
    "sixth|seventh|eighth|ninth|tenth|last|final"
)
_HEADING_PATTERNS = [
    # "CHAPTER I.", "Chapter 12: The Return", "BOOK TWO", "Part III - Ends", "Letter 4"
    re.compile(
        rf"^(?:chapter|book|part|section|letter|canto|act|stave|volume)\s+"
        rf"(?:\d+|[ivxlcdm]+|{_NUM_WORDS})\b[\s.:\-—–]*.{{0,90}}$",
        re.IGNORECASE,
    ),
    # "I. LAYING PLANS", "XII. The End" (roman numeral + title, uppercase numeral)
    re.compile(r"^[IVXLC]{1,7}\.\s+[A-Z][A-Za-z ,;'’\-]{2,80}$"),
    # Standalone "Prologue", "Epilogue", "Introduction"...
    re.compile(r"^(?:prologue|epilogue|introduction|preface|foreword|afterword|conclusion)\b.{0,60}$", re.I),
]

MIN_CHAPTER_CHARS = 300  # shorter "chapters" are TOC entries / title pages
FRONT_MATTER_MIN_CHARS = 1500  # shorter front matter is merged into the first chapter
FALLBACK_SECTION_PAGES = 15


@dataclass
class ChapterData:
    position: int
    title: str
    text: str
    page_map: list[list[int]] = field(default_factory=list)  # [[char_offset, page_number], ...]

    @property
    def start_page(self) -> int | None:
        return self.page_map[0][1] if self.page_map else None

    @property
    def end_page(self) -> int | None:
        return self.page_map[-1][1] if self.page_map else None


def is_heading(text: str) -> bool:
    return len(text) <= 120 and any(p.match(text) for p in _HEADING_PATTERNS)


def _flatten(doc: ParsedDocument) -> list[tuple[int, int, str]]:
    """[(page_index, para_index, text)] in reading order."""
    return [(pi, qi, t) for pi, p in enumerate(doc.pages) for qi, t in enumerate(p.paragraphs)]


def _build(doc: ParsedDocument, flat, starts: list[tuple[int, str]]) -> list[ChapterData]:
    """starts: [(flat_index, title)] sorted. Text before the first start becomes 'Front matter'."""
    if not starts or starts[0][0] > 0:
        starts = [(0, "Front matter")] + starts
    chapters: list[ChapterData] = []
    for n, (begin, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(flat)
        parts: list[str] = []
        page_map: list[list[int]] = []
        offset = 0
        for pi, _, text in flat[begin:end]:
            page_no = doc.pages[pi].number
            if not page_map or page_map[-1][1] != page_no:
                page_map.append([offset, page_no])
            parts.append(text)
            offset += len(text) + len(PARA_SEP)
        body = PARA_SEP.join(parts)
        chapters.append(ChapterData(position=0, title=title[:480], text=body, page_map=page_map))
    return chapters


def _drop_short(chapters: list[ChapterData]) -> list[ChapterData]:
    """Merge tiny sections (TOC lines, title pages) into the following chapter."""
    out: list[ChapterData] = []
    carry: ChapterData | None = None
    for ch in chapters:
        if carry is not None:
            shift = len(carry.text) + len(PARA_SEP)
            ch = ChapterData(
                position=0,
                title=ch.title,
                text=carry.text + PARA_SEP + ch.text,
                page_map=carry.page_map + [[o + shift, p] for o, p in ch.page_map],
            )
            carry = None
        if len(ch.text) < MIN_CHAPTER_CHARS:
            carry = ch
            continue
        out.append(ch)
    if carry is not None:
        if out:
            last = out[-1]
            shift = len(last.text) + len(PARA_SEP)
            last.text += PARA_SEP + carry.text
            last.page_map += [[o + shift, p] for o, p in carry.page_map]
        else:
            out.append(carry)
    # De-duplicate consecutive page_map entries for the same page.
    for ch in out:
        dedup: list[list[int]] = []
        for o, p in ch.page_map:
            if not dedup or dedup[-1][1] != p:
                dedup.append([o, p])
        ch.page_map = dedup
    return out


def _regex_starts(flat) -> list[tuple[int, str]]:
    cands = [(i, t) for i, (_, _, t) in enumerate(flat) if is_heading(t)]
    # A heading followed by a short subtitle paragraph ("CHAPTER I." / "Down the Rabbit-Hole").
    starts = []
    for i, title in cands:
        nxt = flat[i + 1][2] if i + 1 < len(flat) else ""
        if len(title) < 25 and 0 < len(nxt) <= 80 and not is_heading(nxt) and not nxt.endswith((".", ",")):
            title = f"{title.rstrip(' .:')}: {nxt}"
        starts.append((i, title))
    return starts


def detect_chapters(doc: ParsedDocument) -> list[ChapterData]:
    flat = _flatten(doc)
    if not flat:
        return []
    index = {(pi, qi): i for i, (pi, qi, _) in enumerate(flat)}

    starts: list[tuple[int, str]] = []
    for h in doc.headings:
        # Headings can point at an empty page; use the next paragraph that exists.
        key = (h.page_index, h.para_index)
        i = index.get(key)
        if i is None:
            i = next((j for j, (pi, _, _) in enumerate(flat) if pi >= h.page_index), None)
        if i is not None and h.title:
            starts.append((i, h.title))
    starts = sorted(dict(starts).items())  # one title per start index, ordered

    if len(starts) < 2:
        regex = _regex_starts(flat)
        if len(regex) >= 2:
            starts = regex

    if len(starts) >= 2:
        chapters = _drop_short(_build(doc, flat, starts))
        # A short title page / contents list isn't worth its own "chapter" (it would also
        # shift the chapter numbers readers use for the spoiler guard): fold it into chapter 1.
        if len(chapters) > 2 and chapters[0].title == "Front matter" and len(chapters[0].text) < FRONT_MATTER_MIN_CHARS:
            front, first = chapters[0], chapters[1]
            shift = len(front.text) + len(PARA_SEP)
            first.text = front.text + PARA_SEP + first.text
            pm = front.page_map + [[o + shift, p] for o, p in first.page_map]
            first.page_map = [e for i, e in enumerate(pm) if i == 0 or e[1] != pm[i - 1][1]]
            chapters = chapters[1:]
    else:
        chapters = []

    if len(chapters) < 2:
        # No usable structure: fixed-size sections so citations and spoiler guard still work.
        starts = []
        for pi in range(0, len(doc.pages), FALLBACK_SECTION_PAGES):
            i = next((j for j, (p, _, _) in enumerate(flat) if p >= pi), None)
            if i is not None and (not starts or starts[-1][0] != i):
                last = min(pi + FALLBACK_SECTION_PAGES, len(doc.pages))
                label = f"Section {len(starts) + 1} (pages {doc.pages[pi].number}–{doc.pages[last - 1].number})"
                starts.append((i, label))
        chapters = _build(doc, flat, starts)
        if chapters and chapters[0].title == "Front matter" and not chapters[0].text:
            chapters = chapters[1:]

    for n, ch in enumerate(chapters, start=1):
        ch.position = n
    return chapters
