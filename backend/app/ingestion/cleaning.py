"""Text cleaning: page numbers, running headers/footers, boilerplate, unicode noise.

Works on ParsedDocument pages in place and keeps heading indices consistent.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.ingestion.parsers.base import ParsedDocument

_PAGE_NUMBER = re.compile(
    r"^\W*(?:page\s+)?(?:\d{1,4}|[ivxlcdm]{1,7})(?:\s*(?:of|/)\s*\d{1,4})?\W*$", re.IGNORECASE
)
_GUTENBERG_START = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)
_GUTENBERG_END = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f­​﻿]")


def normalize_text(text: str) -> str:
    """NFKC (ligatures -> letters), drop soft hyphens/control chars, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _signature(para: str) -> str:
    """Header/footer fingerprint: case- and digit-insensitive."""
    return re.sub(r"\d+", "#", para.lower()).strip()


def _repeating_margins(doc: ParsedDocument) -> set[str]:
    """Short paragraphs that appear at the top/bottom of many pages (running heads, footers)."""
    n = len(doc.pages)
    if n < 6:
        return set()
    counts: Counter[str] = Counter()
    for page in doc.pages:
        edge = page.paragraphs[:2] + page.paragraphs[-2:]
        counts.update({_signature(p) for p in edge if len(p) < 120})
    threshold = max(3, int(0.3 * n))
    return {sig for sig, c in counts.items() if c >= threshold}


def _strip_gutenberg(doc: ParsedDocument) -> None:
    """Remove Project Gutenberg license header/footer, if present."""
    flat = [(pi, qi) for pi, p in enumerate(doc.pages) for qi in range(len(p.paragraphs))]
    start = end = None
    for pi, qi in flat:
        para = doc.pages[pi].paragraphs[qi]
        if start is None and _GUTENBERG_START.search(para):
            start = (pi, qi)
        elif start is not None and _GUTENBERG_END.search(para):
            end = (pi, qi)
            break
    if start is None:
        return
    for pi, qi in flat:
        if (pi, qi) <= start or (end is not None and (pi, qi) >= end):
            doc.pages[pi].paragraphs[qi] = ""


def clean_document(doc: ParsedDocument) -> ParsedDocument:
    _strip_gutenberg(doc)
    margins = set() if doc.pages_estimated else _repeating_margins(doc)
    heading_keys = {(h.page_index, h.para_index) for h in doc.headings}

    # Mark paragraphs for removal ("" = removed) without shifting indices yet.
    for pi, page in enumerate(doc.pages):
        last = len(page.paragraphs) - 1
        for qi, para in enumerate(page.paragraphs):
            if not para:
                continue
            text = normalize_text(para)
            is_edge = qi < 2 or qi > last - 2
            if _PAGE_NUMBER.match(text) and (pi, qi) not in heading_keys:
                text = ""
            elif is_edge and margins and _signature(text) in margins:
                text = ""
            page.paragraphs[qi] = text

    # Compact paragraphs and remap heading indices to the next surviving paragraph.
    remap: dict[tuple[int, int], int] = {}
    for pi, page in enumerate(doc.pages):
        kept: list[str] = []
        for qi, para in enumerate(page.paragraphs):
            remap[(pi, qi)] = len(kept)
            if para:
                kept.append(para)
        page.paragraphs = kept
    for h in doc.headings:
        h.para_index = remap.get((h.page_index, h.para_index), 0)
        h.title = normalize_text(h.title)
    return doc
