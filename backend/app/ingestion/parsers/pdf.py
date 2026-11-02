"""PDF parsing with PyMuPDF, with optional Tesseract OCR for scanned pages."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pymupdf

from app.ingestion.parsers.base import Heading, Page, ParsedDocument, ParseError, ProgressFn, join_lines

_MIN_CHARS_PER_PAGE = 20  # below this a page is considered "no text layer"


def tesseract_available() -> bool:
    if shutil.which("tesseract"):
        return True
    win = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
    return win.exists()


def _ensure_tesseract_env() -> None:
    """PyMuPDF needs TESSDATA_PREFIX; fill it in for default installs if unset."""
    if os.environ.get("TESSDATA_PREFIX"):
        return
    try:
        os.environ["TESSDATA_PREFIX"] = pymupdf.get_tessdata()
    except Exception:  # noqa: BLE001 - best effort only
        win = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tessdata"
        if win.exists():
            os.environ["TESSDATA_PREFIX"] = str(win)


def _page_paragraphs(page: pymupdf.Page, textpage=None) -> list[str]:
    blocks = page.get_text("blocks", sort=True, textpage=textpage)
    paras = []
    for b in blocks:
        if b[6] != 0:  # 0 = text block, 1 = image
            continue
        text = join_lines(b[4].splitlines())
        if text:
            paras.append(text)
    return paras


def parse_pdf(path: Path, progress: ProgressFn) -> ParsedDocument:
    try:
        doc = pymupdf.open(path)
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"This PDF could not be opened (it may be corrupted): {e}") from e
    if doc.needs_pass:
        raise ParseError("This PDF is password-protected. Remove the password and upload it again.")

    out = ParsedDocument()
    meta = doc.metadata or {}
    out.title = (meta.get("title") or "").strip() or None
    out.author = (meta.get("author") or "").strip() or None

    ocr_ok = tesseract_available()
    if ocr_ok:
        _ensure_tesseract_env()
    empty_pages = ocr_pages = 0
    n = doc.page_count
    for i, page in enumerate(doc):
        paras = _page_paragraphs(page)
        if sum(len(p) for p in paras) < _MIN_CHARS_PER_PAGE and page.get_images():
            if ocr_ok:
                try:
                    tp = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                    paras = _page_paragraphs(page, textpage=tp)
                    ocr_pages += 1
                except Exception:  # noqa: BLE001 - OCR failure on one page shouldn't kill the book
                    empty_pages += 1
            else:
                empty_pages += 1
        out.pages.append(Page(number=i + 1, paragraphs=paras))
        if i % 10 == 0:
            progress(i / max(n, 1), f"Reading page {i + 1} of {n}")

    if empty_pages and empty_pages >= 0.5 * n:
        if sum(len(p.paragraphs) for p in out.pages) == 0:
            raise ParseError(
                "This PDF looks scanned (images only, no text layer) and Tesseract OCR is not installed. "
                "Install Tesseract (see README) and re-index, or upload a text-based PDF/EPUB."
            )
        out.warnings.append(
            f"{empty_pages} of {n} pages appear to be scanned images without text and were skipped. "
            "Install Tesseract OCR and re-index to include them."
        )
    elif empty_pages:
        out.warnings.append(f"{empty_pages} page(s) contained no extractable text.")
    if ocr_pages:
        out.warnings.append(f"{ocr_pages} page(s) were read with OCR; expect some recognition errors.")

    # Chapters from the PDF outline (bookmarks), when present.
    toc = doc.get_toc(simple=True)  # [[level, title, page(1-based)], ...]
    if toc:
        top = min(level for level, _, _ in toc)
        entries = [(t, p) for level, t, p in toc if level == top and p >= 1]
        if len(entries) <= 2:  # a single "Book" root: use the next level instead
            entries = [(t, p) for level, t, p in toc if level == top + 1 and p >= 1] or entries
        for title, pno in entries:
            out.headings.append(Heading(page_index=min(pno, n) - 1, para_index=0, title=title.strip()))
    doc.close()
    return out
