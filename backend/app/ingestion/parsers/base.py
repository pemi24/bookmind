"""Common types every parser produces.

A parser turns a file into pages of paragraphs plus optional explicit headings
(from a PDF outline, EPUB TOC, DOCX heading styles, Markdown #). Cleaning and
chapter detection then work on this format, independent of the source type.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

ProgressFn = Callable[[float, str], None]  # (fraction 0..1, message)

SYNTHETIC_PAGE_CHARS = 2000  # for formats without real pages (EPUB/DOCX/TXT)


class ParseError(Exception):
    """Raised with a message that is safe to show to the user."""


@dataclass
class Page:
    number: int  # 1-based, as shown to the user
    paragraphs: list[str]


@dataclass
class Heading:
    page_index: int  # index into ParsedDocument.pages
    para_index: int  # index into that page's paragraphs
    title: str


@dataclass
class ParsedDocument:
    title: str | None = None
    author: str | None = None
    pages: list[Page] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)
    pages_estimated: bool = False
    warnings: list[str] = field(default_factory=list)


def join_lines(lines: list[str]) -> str:
    """Unwrap hard line breaks inside a paragraph, repairing end-of-line hyphenation."""
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
        elif re.search(r"[a-z]-$", out) and line[:1].islower():
            out = out[:-1] + line  # "exam-" + "ple" -> "example"
        else:
            out += " " + line
    return out


class Paginator:
    """Groups a paragraph stream into synthetic pages of ~SYNTHETIC_PAGE_CHARS."""

    def __init__(self, doc: ParsedDocument) -> None:
        self.doc = doc
        self._buf: list[str] = []
        self._size = 0

    def _flush(self) -> None:
        if self._buf:
            self.doc.pages.append(Page(number=len(self.doc.pages) + 1, paragraphs=self._buf))
            self._buf, self._size = [], 0

    def heading(self, title: str) -> None:
        """Start a new page and record a chapter heading at its top."""
        self._flush()
        self.doc.headings.append(Heading(page_index=len(self.doc.pages), para_index=0, title=title))

    def add(self, para: str) -> None:
        para = para.strip()
        if not para:
            return
        if self._size and self._size + len(para) > SYNTHETIC_PAGE_CHARS:
            self._flush()
        self._buf.append(para)
        self._size += len(para)

    def finish(self) -> ParsedDocument:
        self._flush()
        # Drop headings that ended up pointing past the last page (empty trailing sections).
        self.doc.headings = [h for h in self.doc.headings if h.page_index < len(self.doc.pages)]
        self.doc.pages_estimated = True
        return self.doc
