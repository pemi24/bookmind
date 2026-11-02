"""DOCX parsing with python-docx. Heading styles become chapters."""
from __future__ import annotations

from pathlib import Path

import docx

from app.ingestion.parsers.base import Paginator, ParsedDocument, ParseError, ProgressFn


def _heading_level(style_name: str) -> int | None:
    name = (style_name or "").lower()
    if name == "title":
        return 0
    if name.startswith("heading"):
        try:
            return int(name.split()[-1])
        except ValueError:
            return 1
    return None


def parse_docx(path: Path, progress: ProgressFn) -> ParsedDocument:
    try:
        d = docx.Document(str(path))
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"This DOCX could not be opened (old .doc files are not supported): {e}") from e

    out = ParsedDocument()
    props = d.core_properties
    out.title = (props.title or "").strip() or None
    out.author = (props.author or "").strip() or None

    paras = [(p.text.strip(), _heading_level(p.style.name if p.style else "")) for p in d.paragraphs]
    paras = [(t, lvl) for t, lvl in paras if t]
    levels = sorted({lvl for _, lvl in paras if lvl and lvl > 0})
    chapter_level = levels[0] if levels else None

    pager = Paginator(out)
    for i, (text, lvl) in enumerate(paras):
        if chapter_level is not None and lvl == chapter_level and len(text) < 200:
            pager.heading(text)
        elif lvl == 0 and not out.title:
            out.title = text
        pager.add(text)
        if i % 200 == 0:
            progress(i / max(len(paras), 1), "Reading document")
    return pager.finish()
