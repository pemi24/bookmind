"""Dispatch a file to the right parser by extension."""
from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.base import Heading, Page, ParsedDocument, ParseError, ProgressFn

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".docx", ".txt", ".md", ".markdown"}


def parse_file(path: Path, progress: ProgressFn = lambda f, m: None) -> ParsedDocument:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from app.ingestion.parsers.pdf import parse_pdf

        return parse_pdf(path, progress)
    if ext == ".epub":
        from app.ingestion.parsers.epub import parse_epub

        return parse_epub(path, progress)
    if ext == ".docx":
        from app.ingestion.parsers.word import parse_docx

        return parse_docx(path, progress)
    if ext in (".txt", ".md", ".markdown"):
        from app.ingestion.parsers.text import parse_text

        return parse_text(path, progress, markdown=ext != ".txt")
    raise ParseError(f"Unsupported file type '{ext}'. Supported: PDF, EPUB, DOCX, TXT, MD.")


__all__ = ["Heading", "Page", "ParsedDocument", "ParseError", "SUPPORTED_EXTENSIONS", "parse_file"]
