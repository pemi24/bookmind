"""Plain text and Markdown parsing (including Project Gutenberg .txt files)."""
from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.parsers.base import Paginator, ParsedDocument, ParseError, ProgressFn, join_lines

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# _italic_ / *emphasis* markup (Gutenberg .txt convention, Markdown): keep the words only.
_EMPHASIS = re.compile(r"(?<![\w*_])([_*]{1,2})(?=[^\s*_])(.+?)(?<=[^\s*_])\1(?![\w*_])")


def _strip_emphasis(text: str) -> str:
    return _EMPHASIS.sub(r"\2", text)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and "\x00" in text:
                continue
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


def _gutenberg_meta(text: str) -> tuple[str | None, str | None]:
    head = text[:5000]
    t = re.search(r"^Title:\s*(.+)$", head, re.M)
    a = re.search(r"^Author:\s*(.+)$", head, re.M)
    return (t.group(1).strip() if t else None, a.group(1).strip() if a else None)


def parse_text(path: Path, progress: ProgressFn, markdown: bool = False) -> ParsedDocument:
    raw = path.read_bytes()
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ParseError("This file looks binary, not text. Supported formats: PDF, EPUB, DOCX, TXT, MD.")
    text = _strip_emphasis(_decode(raw).replace("\r\n", "\n").replace("\r", "\n"))

    out = ParsedDocument()
    out.title, out.author = _gutenberg_meta(text)
    pager = Paginator(out)

    blocks = re.split(r"\n\s*\n", text)
    md_level = None
    if markdown:
        levels = [len(m.group(1)) for b in blocks for line in b.split("\n") if (m := _MD_HEADING.match(line))]
        md_level = min(levels) if levels else None

    for i, block in enumerate(blocks):
        lines = block.split("\n")
        if markdown:
            # A Markdown heading can share a block with following text.
            buf: list[str] = []
            for line in lines:
                m = _MD_HEADING.match(line)
                if m:
                    if buf:
                        pager.add(join_lines(buf))
                        buf = []
                    if len(m.group(1)) == md_level:
                        pager.heading(m.group(2))
                        if not out.title and md_level == 1 and not out.headings[:-1]:
                            out.title = m.group(2)
                    pager.add(m.group(2))
                else:
                    buf.append(line)
            if buf:
                pager.add(join_lines(buf))
        else:
            pager.add(join_lines(lines))
        if i % 500 == 0:
            progress(i / max(len(blocks), 1), "Reading text")
    return pager.finish()
