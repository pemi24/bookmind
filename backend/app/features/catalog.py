"""Free-book finder: search Project Gutenberg's official catalog (OPDS feed) and download a book.

Downloads always use Gutenberg's own links for a numeric book id, never a URL sent by the
browser, and only from gutenberg.org.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from app.config import get_settings

_ATOM = "{http://www.w3.org/2005/Atom}"
_BOOK_ID = re.compile(r"/ebooks/(\d+)\.opds$")
# Best first: EPUB keeps the chapter structure; plain text is the fallback.
_DOWNLOADS = [("epub.noimages", ".epub"), ("txt.utf-8", ".txt")]
_ALLOWED_HOSTS = ("gutenberg.org", "www.gutenberg.org", "gutenberg.pglaf.org", "aleph.gutenberg.org")
PAGE_SIZE = 25


class CatalogError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _base() -> str:
    return get_settings().catalog_url.rstrip("/")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True,
                             headers={"User-Agent": "BookMind (local reading app)"})


# One retry for "busy" answers, and a small cache: the catalog changes rarely.
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 3600.0
_CACHE_MAX = 200


async def _get_text(path: str, params: dict | None = None) -> str:
    key = f"{path}?{sorted((params or {}).items())}"
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    r = None
    for attempt in range(2):
        try:
            async with _client() as c:
                r = await c.get(f"{_base()}{path}", params=params)
        except httpx.TimeoutException as e:
            raise CatalogError("Project Gutenberg is very slow right now. Try again in a minute.", 503) from e
        except httpx.HTTPError as e:
            raise CatalogError("Can't reach Project Gutenberg. Check your internet connection.", 503) from e
        if r.status_code not in (429, 502, 503, 504) or attempt:
            break
        await asyncio.sleep(2)
    if r.status_code == 404:
        raise CatalogError("That book isn't in the Project Gutenberg catalog.", 404)
    if r.status_code != 200:
        raise CatalogError(f"Project Gutenberg is busy or down ({r.status_code}). Try again in a minute.", 503)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (time.monotonic(), r.text)
    return r.text


def _feed(xml: str) -> ET.Element:
    try:
        return ET.fromstring(xml)
    except ET.ParseError as e:
        raise CatalogError("Project Gutenberg sent an unreadable answer. Try again later.", 502) from e


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_search(xml: str) -> dict:
    root = _feed(xml)
    results = []
    for entry in root.iter(f"{_ATOM}entry"):
        m = _BOOK_ID.search(_text(entry.find(f"{_ATOM}id")))
        if not m:
            continue  # "Authors" / "Subjects" sub-sections, sort links...
        book_id = int(m.group(1))
        results.append({
            "id": book_id,
            "title": _text(entry.find(f"{_ATOM}title")) or "Untitled",
            "author": search_name(_text(entry.find(f"{_ATOM}content"))),
            "cover": f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.cover.medium.jpg",
            "url": f"https://www.gutenberg.org/ebooks/{book_id}",
        })
    has_more = any(link.get("rel") == "next" for link in root.iter(f"{_ATOM}link"))
    return {"results": results, "has_more": has_more}


async def search(query: str, page: int) -> dict:
    """Search by title, author or subject; an empty query lists the most downloaded books."""
    params: dict = {"start_index": (page - 1) * PAGE_SIZE + 1}
    if query:
        params["query"] = query
    else:
        params["sort_order"] = "downloads"
    return parse_search(await _get_text("/ebooks/search.opds/", params))


def parse_book(xml: str) -> dict:
    root = _feed(xml)
    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        raise CatalogError("That book isn't in the Project Gutenberg catalog.", 404)
    return {"title": _text(entry.find(f"{_ATOM}title")) or "Untitled",
            "author": catalog_name(_text(entry.find(f"{_ATOM}author/{_ATOM}name")))}


_LIFESPAN = re.compile(r"\d|^(?:active|fl\.|approximately|ca\.|b\.|d\.)\b", re.I)


def catalog_name(name: str) -> str | None:
    """Gutenberg's "Carroll, Lewis, 1832-1898" / "Sunzi, active 6th century B.C." -> "Lewis Carroll" / "Sunzi"."""
    parts = [p.strip() for p in name.split(",") if p.strip() and not _LIFESPAN.search(p.strip())]
    if not parts:
        return None
    return f"{parts[1]} {parts[0]}" if len(parts) > 1 else parts[0]


def search_name(text: str) -> str | None:
    """Search results show "active 6th century B.C. Sunzi" / "Lewis Carroll": drop leading dates."""
    text = re.sub(r"^(?:active|fl\.)?\s*[\w.\-? ]*?(?:century|\d{3,4})(?:\s*(?:B\.C\.|BC|A\.D\.|AD))?\s+", "", text,
                  flags=re.I)
    return text.strip() or None


async def download(gutenberg_id: int) -> dict:
    """Fetch a book's metadata and file. Returns title/author/path/size/ext/filename for a new Book row."""
    meta = parse_book(await _get_text(f"/ebooks/{gutenberg_id}.opds"))
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    last_status = 0
    for kind, ext in _DOWNLOADS:
        dest = s.upload_dir / f"{uuid.uuid4().hex}{ext}"
        size = 0
        try:
            async with _client() as c, c.stream("GET", f"{_base()}/ebooks/{gutenberg_id}.{kind}") as r:
                last_status = r.status_code
                if r.status_code != 200 or urlparse(str(r.url)).hostname not in _ALLOWED_HOSTS:
                    continue
                with dest.open("wb") as out:
                    async for chunk in r.aiter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise CatalogError(f"The book is larger than the {s.max_upload_mb} MB limit.", 413)
                        out.write(chunk)
        except httpx.HTTPError as e:
            dest.unlink(missing_ok=True)
            raise CatalogError("The download was interrupted. Check your internet connection and try again.", 503) from e
        except CatalogError:
            dest.unlink(missing_ok=True)
            raise
        if size == 0:
            dest.unlink(missing_ok=True)
            continue
        return {**meta, "path": dest, "size": size, "ext": ext, "filename": f"gutenberg-{gutenberg_id}{ext}"}
    raise CatalogError(f"Project Gutenberg has no downloadable EPUB or text edition of this book ({last_status}).", 422)
