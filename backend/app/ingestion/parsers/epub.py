"""EPUB parsing with ebooklib + BeautifulSoup."""
from __future__ import annotations

import posixpath
import warnings
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from app.ingestion.parsers.base import Paginator, ParsedDocument, ParseError, ProgressFn

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")
warnings.filterwarnings("ignore", category=FutureWarning, module="ebooklib")

_BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "dd", "dt"]


def _toc_titles(book: epub.EpubBook) -> dict[str, str]:
    """Map document href (without #fragment) -> first TOC title pointing at it."""
    titles: dict[str, str] = {}

    def walk(items) -> None:
        for item in items:
            if isinstance(item, tuple):  # (Section, [children])
                section, children = item
                href = getattr(section, "href", None)
                if href:
                    titles.setdefault(href.split("#")[0], section.title)
                walk(children)
            elif isinstance(item, epub.Link):
                titles.setdefault(item.href.split("#")[0], item.title)

    walk(book.toc)
    return titles


def _paragraphs(html: bytes) -> tuple[list[str], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav"]):
        t.decompose()
    first_heading = None
    paras: list[str] = []
    for el in soup.find_all(_BLOCK_TAGS):
        if el.find_parent(_BLOCK_TAGS):  # nested block: its parent already captured the text
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if first_heading is None and el.name in ("h1", "h2", "h3") and len(text) < 150:
            first_heading = text
        paras.append(text)
    if not paras:  # documents made of bare <div>s / <br>s
        body = soup.body or soup
        paras = [" ".join(p.split()) for p in body.get_text("\n").split("\n\n") if p.strip()]
    return paras, first_heading


def parse_epub(path: Path, progress: ProgressFn) -> ParsedDocument:
    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": False})
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"This EPUB could not be read (it may be corrupted or DRM-protected): {e}") from e

    out = ParsedDocument()
    t = book.get_metadata("DC", "title")
    a = book.get_metadata("DC", "creator")
    out.title = t[0][0].strip() if t else None
    out.author = a[0][0].strip() if a else None

    toc = _toc_titles(book)
    pager = Paginator(out)
    spine = [book.get_item_with_id(idref) for idref, _ in book.spine]
    docs = [it for it in spine if it is not None and it.get_type() == ebooklib.ITEM_DOCUMENT]
    if not docs:
        raise ParseError("This EPUB has no readable text documents.")

    for i, item in enumerate(docs):
        paras, first_heading = _paragraphs(item.get_content())
        if not paras:
            continue
        name = item.get_name()
        title = toc.get(name) or toc.get(posixpath.basename(name)) or first_heading
        if title:
            pager.heading(title.strip())
        for p in paras:
            pager.add(p)
        progress((i + 1) / len(docs), f"Reading section {i + 1} of {len(docs)}")
    return pager.finish()
