"""Free-book finder: search several legal sources of free books at once and download one.

Sources (all public-domain / free to download):
  * Project Gutenberg  — official OPDS search feed; EPUB or plain text.
  * Standard Ebooks    — carefully edited public-domain ebooks; OPDS search feed; EPUB.
  * Internet Archive   — library scans; only items the Archive itself marks NOT_IN_COPYRIGHT and that
                         aren't loan-only (anyone can upload to the Archive, so this filter matters).

Downloads never use a URL sent by the browser: the server rebuilds each source's own link from the
book's id (re-checking Internet Archive items' copyright status first) and only follows redirects
within that source's own hosts.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx

from app.config import get_settings
from app.features.common import normalize_name

_ATOM = "{http://www.w3.org/2005/Atom}"
PAGE_SIZE = 25
SOURCE_TIMEOUT = 30.0  # one slow source must not hold up the others


class CatalogError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True,
                             headers={"User-Agent": "BookMind (local reading app)"})


# One retry for "busy" answers, and a small cache: catalogs change rarely.
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 3600.0
_CACHE_MAX = 300


async def _get_text(url: str, params: dict | None, label: str) -> str:
    key = f"{url}?{sorted((params or {}).items())}"
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    r = None
    for attempt in range(2):
        try:
            async with _client() as c:
                r = await c.get(url, params=params)
        except httpx.TimeoutException as e:
            raise CatalogError(f"{label} is very slow right now. Try again in a minute.", 503) from e
        except httpx.HTTPError as e:
            raise CatalogError(f"Can't reach {label}. Check your internet connection.", 503) from e
        if r.status_code not in (429, 502, 503, 504) or attempt:
            break
        await asyncio.sleep(2)
    if r.status_code == 404:
        raise CatalogError(f"That book isn't in the {label} catalog.", 404)
    if r.status_code != 200:
        raise CatalogError(f"{label} is busy or down ({r.status_code}). Try again in a minute.", 503)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (time.monotonic(), r.text)
    return r.text


def _feed(xml: str, label: str) -> ET.Element:
    try:
        return ET.fromstring(xml)
    except ET.ParseError as e:
        raise CatalogError(f"{label} sent an unreadable answer. Try again later.", 502) from e


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _has_next(root: ET.Element) -> bool:
    return any(link.get("rel") == "next" for link in root.iter(f"{_ATOM}link"))


_LIFESPAN = re.compile(r"\d|^(?:active|fl\.|approximately|ca\.|b\.|d\.)\b", re.I)


def catalog_name(name: str) -> str | None:
    """Library-style "Carroll, Lewis, 1832-1898" / "Sunzi, active 6th century B.C." -> "Lewis Carroll" / "Sunzi"."""
    parts = [p.strip() for p in name.split(",") if p.strip() and not _LIFESPAN.search(p.strip())]
    if not parts:
        return None
    if len(parts) == 1 or _HONORIFIC.match(parts[1]):  # "Marcus Aurelius, Emperor of Rome" -> "Marcus Aurelius"
        return parts[0]
    return f"{parts[1]} {parts[0]}"


_HONORIFIC = re.compile(r"(?:emperor|empress|king|queen|pope|saint|st\.|lord|lady|sir|baron|duke|earl|count|"
                        r"bishop|cardinal|prince|princess)\b", re.I)


def search_name(text: str) -> str | None:
    """Gutenberg search results show "active 6th century B.C. Sunzi" / "Lewis Carroll": drop leading dates."""
    text = re.sub(r"^(?:active|fl\.)?\s*[\w.\-? ]*?(?:century|\d{3,4})(?:\s*(?:B\.C\.|BC|A\.D\.|AD))?\s+", "", text,
                  flags=re.I)
    text = re.sub(r"^(?:Emperor|Empress|King|Queen|Pope|Saint|Bishop) of \w+ ", "", text)  # "Emperor of Rome Marcus Aurelius"
    return text.strip() or None


# ---------------------------------------------------------------- downloads (shared)

async def _download(candidates: list[tuple[str, str]], host_ok: Callable[[str], bool], label: str,
                    dest_dir: Path) -> tuple:
    """Try each (url, ext) in order; returns (path, size, ext). Stays within the source's own hosts."""
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    last_status = 0
    for url, ext in candidates:
        dest = dest_dir / f"{uuid.uuid4().hex}{ext}"
        size = 0
        try:
            async with _client() as c, c.stream("GET", url) as r:
                last_status = r.status_code
                if r.status_code != 200 or not host_ok(urlparse(str(r.url)).hostname or ""):
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
        return dest, size, ext
    raise CatalogError(f"{label} has no downloadable EPUB or text edition of this book ({last_status}).", 422)


# ---------------------------------------------------------------- Project Gutenberg

_GUTENBERG_ID = re.compile(r"/ebooks/(\d+)\.opds$")
_GUTENBERG_HOSTS = ("gutenberg.org", "www.gutenberg.org", "gutenberg.pglaf.org", "aleph.gutenberg.org")


def _gutenberg_base() -> str:
    return get_settings().catalog_url.rstrip("/")


def parse_search(xml: str) -> dict:
    """Gutenberg OPDS search results."""
    root = _feed(xml, "Project Gutenberg")
    results = []
    for entry in root.iter(f"{_ATOM}entry"):
        m = _GUTENBERG_ID.search(_text(entry.find(f"{_ATOM}id")))
        if not m:
            continue  # "Authors" / "Subjects" sub-sections, sort links...
        book_id = m.group(1)
        results.append({
            "source": "gutenberg", "id": book_id,
            "title": _text(entry.find(f"{_ATOM}title")) or "Untitled",
            "author": search_name(_text(entry.find(f"{_ATOM}content"))),
            "cover": f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.cover.medium.jpg",
            "url": f"https://www.gutenberg.org/ebooks/{book_id}",
        })
    return {"results": results, "has_more": _has_next(root)}


def parse_book(xml: str) -> dict:
    entry = _feed(xml, "Project Gutenberg").find(f"{_ATOM}entry")
    if entry is None:
        raise CatalogError("That book isn't in the Project Gutenberg catalog.", 404)
    return {"title": _text(entry.find(f"{_ATOM}title")) or "Untitled",
            "author": catalog_name(_text(entry.find(f"{_ATOM}author/{_ATOM}name")))}


async def _gutenberg_search(query: str, page: int) -> dict:
    params: dict = {"start_index": (page - 1) * PAGE_SIZE + 1}
    if query:
        params["query"] = query
    else:
        params["sort_order"] = "downloads"
    return parse_search(await _get_text(f"{_gutenberg_base()}/ebooks/search.opds/", params, "Project Gutenberg"))


async def _gutenberg_download(book_id: str, dest_dir: Path) -> dict:
    if not re.fullmatch(r"\d{1,7}", book_id):
        raise CatalogError("Not a Project Gutenberg book number.", 400)
    meta = parse_book(await _get_text(f"{_gutenberg_base()}/ebooks/{book_id}.opds", None, "Project Gutenberg"))
    base = _gutenberg_base()
    path, size, ext = await _download(
        [(f"{base}/ebooks/{book_id}.epub.noimages", ".epub"), (f"{base}/ebooks/{book_id}.txt.utf-8", ".txt")],
        lambda h: h in _GUTENBERG_HOSTS, "Project Gutenberg", dest_dir)
    return {**meta, "path": path, "size": size, "ext": ext}


# ---------------------------------------------------------------- Standard Ebooks

_SE = "https://standardebooks.org"
_SE_ID = re.compile(r"[a-z0-9-]+(?:/[a-z0-9_-]+){1,4}")


def parse_standard_search(xml: str) -> dict:
    root = _feed(xml, "Standard Ebooks")
    results = []
    for entry in root.iter(f"{_ATOM}entry"):
        url = _text(entry.find(f"{_ATOM}id"))
        m = re.match(r"https://standardebooks\.org/ebooks/(.+)$", url)
        if not m or not _SE_ID.fullmatch(m.group(1)):
            continue
        authors = [_text(a.find(f"{_ATOM}name")) for a in entry.findall(f"{_ATOM}author")]
        cover = next((link.get("href") for link in entry.findall(f"{_ATOM}link")
                      if link.get("rel") == "http://opds-spec.org/image/thumbnail"), None)
        results.append({
            "source": "standard", "id": m.group(1), "title": _text(entry.find(f"{_ATOM}title")) or "Untitled",
            "author": ", ".join(a for a in authors if a) or None, "cover": cover or "", "url": url,
        })
    return {"results": results, "has_more": _has_next(root)}


async def _standard_search(query: str, page: int) -> dict:
    xml = await _get_text(f"{_SE}/feeds/opds/all", {"query": query, "page": page, "per-page": 12}, "Standard Ebooks")
    return parse_standard_search(xml)


def standard_epub_url(book_id: str) -> str:
    """Standard Ebooks names files after the book's path: bram-stoker/dracula -> bram-stoker_dracula.epub."""
    return f"{_SE}/ebooks/{book_id}/downloads/{book_id.replace('/', '_')}.epub?source=feed"


async def _standard_download(book_id: str, dest_dir: Path) -> dict:
    if not _SE_ID.fullmatch(book_id):
        raise CatalogError("Not a Standard Ebooks book.", 400)
    path, size, ext = await _download([(standard_epub_url(book_id), ".epub")],
                                      lambda h: h in ("standardebooks.org", "www.standardebooks.org"),
                                      "Standard Ebooks", dest_dir)
    return {"title": None, "author": None, "path": path, "size": size, "ext": ext}  # read from the EPUB


# ---------------------------------------------------------------- Internet Archive

_IA = "https://archive.org"
_IA_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_IA_LENDING = {"inlibrary", "printdisabled", "lendinglibrary"}
# Only items the Archive itself judged out of copyright, and never loan-only ones.
_IA_FILTER = ('mediatype:texts AND possible-copyright-status:"NOT_IN_COPYRIGHT" AND NOT access-restricted-item:true '
              "AND NOT collection:(inlibrary OR printdisabled OR lendinglibrary) AND format:(EPUB OR DjVuTXT)")


def _ia_terms(query: str) -> str:
    words = re.findall(r"[\w']+", query)[:12]
    return " ".join(w.replace("'", "") for w in words)


def _first(v) -> str:
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "")


def parse_archive_search(data: dict) -> dict:
    docs = (data.get("response") or {}).get("docs") or []
    results, seen = [], set()
    for d in docs:
        ident = str(d.get("identifier", ""))
        if not _IA_ID.fullmatch(ident):
            continue
        title = _first(d.get("title")) or "Untitled"
        author = catalog_name(_first(d.get("creator"))) if d.get("creator") else None
        key = (normalize_name(title), normalize_name(author or ""))
        if key in seen:
            continue  # the Archive often holds several scans of the same edition
        seen.add(key)
        year = _first(d.get("year"))
        results.append({
            "source": "archive", "id": ident, "title": title + (f" ({year})" if year.isdigit() else ""),
            "author": author, "cover": f"{_IA}/services/img/{ident}", "url": f"{_IA}/details/{ident}",
        })
    return {"results": results, "total": (data.get("response") or {}).get("numFound", 0)}


async def _archive_search(query: str, page: int) -> dict:
    terms = _ia_terms(query)
    if not terms:
        return {"results": [], "has_more": False}
    params = {"q": f"(title:({terms}) OR creator:({terms})) AND {_IA_FILTER}",
              "fl[]": ["identifier", "title", "creator", "year"], "sort[]": "downloads desc",
              "rows": 12, "page": page, "output": "json"}
    text = await _get_text(f"{_IA}/advancedsearch.php", params, "Internet Archive")
    try:
        parsed = parse_archive_search(json.loads(text))
    except ValueError as e:
        raise CatalogError("Internet Archive sent an unreadable answer. Try again later.", 502) from e
    return {"results": parsed["results"], "has_more": parsed["total"] > page * 12}


def archive_files(ident: str, meta: dict) -> list[tuple[str, str]]:
    """Check an item is free to download, then pick its files: EPUB first, else the scan's plain text."""
    md = meta.get("metadata") or {}
    if not md:
        raise CatalogError("That book isn't in the Internet Archive catalog.", 404)
    collections = md.get("collection") or []
    collections = {collections} if isinstance(collections, str) else set(collections)
    if (md.get("possible-copyright-status") != "NOT_IN_COPYRIGHT" or str(md.get("access-restricted-item")).lower() == "true"
            or collections & _IA_LENDING):
        raise CatalogError("This Internet Archive item isn't marked as free to download, so BookMind won't fetch it.", 403)
    files = [f for f in meta.get("files") or [] if not f.get("private")]
    picks = [f["name"] for f in files if f.get("format") == "EPUB"] + \
            [f["name"] for f in files if f.get("format") == "DjVuTXT"]
    return [(f"{_IA}/download/{ident}/{quote(name)}", ".epub" if name.endswith(".epub") else ".txt") for name in picks]


async def _archive_download(ident: str, dest_dir: Path) -> dict:
    if not _IA_ID.fullmatch(ident):
        raise CatalogError("Not an Internet Archive item.", 400)
    try:
        meta = json.loads(await _get_text(f"{_IA}/metadata/{ident}", None, "Internet Archive"))
    except ValueError as e:
        raise CatalogError("Internet Archive sent an unreadable answer. Try again later.", 502) from e
    candidates = archive_files(ident, meta)
    md = meta["metadata"]
    path, size, ext = await _download(candidates, lambda h: h == "archive.org" or h.endswith(".archive.org"),
                                      "Internet Archive", dest_dir)
    return {"title": _first(md.get("title")) or None, "author": catalog_name(_first(md.get("creator"))),
            "path": path, "size": size, "ext": ext}


# ---------------------------------------------------------------- all sources

@dataclass(frozen=True)
class Source:
    key: str
    name: str
    search: Callable[[str, int], Awaitable[dict]]
    download: Callable[[str, Path], Awaitable[dict]]


SOURCES = [
    Source("gutenberg", "Project Gutenberg", _gutenberg_search, _gutenberg_download),
    Source("standard", "Standard Ebooks", _standard_search, _standard_download),
    Source("archive", "Internet Archive", _archive_search, _archive_download),
]
BY_KEY = {s.key: s for s in SOURCES}


async def search(query: str, page: int, sources: list[str] | None = None) -> dict:
    """Search the sources at once (Gutenberg's results first). A source that fails or is slow is reported
    in `sources`, and the others still answer. An empty query lists Gutenberg's most downloaded books."""
    chosen = [BY_KEY[k] for k in (sources or BY_KEY) if k in BY_KEY] or SOURCES
    if not query:
        chosen = [BY_KEY["gutenberg"]]

    async def run(src: Source) -> dict:
        return await asyncio.wait_for(src.search(query, page), SOURCE_TIMEOUT)

    outcomes = await asyncio.gather(*(run(s) for s in chosen), return_exceptions=True)
    results, status, has_more = [], [], False
    for src, out in zip(chosen, outcomes):
        if isinstance(out, CatalogError):
            status.append({"key": src.key, "name": src.name, "count": 0, "error": out.message})
        elif isinstance(out, asyncio.TimeoutError):
            status.append({"key": src.key, "name": src.name, "count": 0, "error": f"{src.name} took too long to answer."})
        elif isinstance(out, Exception):
            status.append({"key": src.key, "name": src.name, "count": 0, "error": f"{src.name} couldn't be searched."})
        else:
            results.extend(out["results"])
            has_more = has_more or out["has_more"]
            status.append({"key": src.key, "name": src.name, "count": len(out["results"]), "error": None})
    return {"results": results, "has_more": has_more, "sources": status}


async def download(source: str, book_id: str, dest_dir: Path) -> dict:
    """Fetch a book's file (and metadata where the source offers it). Returns title/author/path/size/ext/filename."""
    src = BY_KEY.get(source)
    if src is None:
        raise CatalogError("Unknown book source.", 400)
    got = await src.download(book_id, dest_dir)
    return {**got, "filename": f"{download_prefix(source, book_id)}{got['ext'].lstrip('.')}"}


def download_prefix(source: str, book_id: str) -> str:
    """File names identify where a book came from ("gutenberg-132.epub"), so re-adding it is caught."""
    return f"{source}-{re.sub(r'[^A-Za-z0-9-]+', '_', book_id)[:100]}."
