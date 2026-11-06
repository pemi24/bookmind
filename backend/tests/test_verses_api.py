"""Books with verses through the API: indexing, verse lookup and links, read-aloud items, citations,
turning detection off, and ownership (someone else's book is a 404, never a 403)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import pytest

from tests.conftest import signed_in

pytestmark = pytest.mark.asyncio(loop_scope="session")

SAMPLE = (Path(__file__).parent / "data" / "kjv_sample.txt").read_bytes()
MARKER = re.compile(r"\b\d{1,3}\s*[:.]\s*\d{1,3}\b|\[\d")


async def _ready(c: httpx.AsyncClient, book_id: int, timeout: float = 300) -> dict:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        b = (await c.get(f"/api/books/{book_id}")).json()
        if b["status"] in ("ready", "failed"):
            return b
        await asyncio.sleep(0.5)
    raise TimeoutError("indexing did not finish")


async def _upload(c: httpx.AsyncClient) -> dict:
    r = await c.post("/api/books", files={"file": ("KJV sample.txt", SAMPLE, "text/plain")})
    assert r.status_code == 201, r.text
    book = await _ready(c, r.json()["id"])
    assert book["status"] == "ready", book
    return book


async def test_book_with_verses_end_to_end(test_db):
    from app.main import app

    async with signed_in(app) as a, signed_in(app) as b:
        book = await _upload(a)
        bid = book["id"]
        assert book["verses"] == {"sections": 4, "chapters": 7, "verses": 155, "summary": "Detected 4 books, 7 chapters, 155 verses"}
        assert book["status_message"].startswith("Detected 4 books, 7 chapters, 155 verses")

        chapters = (await a.get(f"/api/books/{bid}/chapters")).json()
        assert [(c["title"], c["section"], c["number"]) for c in chapters][:3] == [
            ("Genesis 1", "Genesis", 1), ("Genesis 2", "Genesis", 2), ("Psalm 3", "Psalms", 3)]
        john3 = next(c for c in chapters if c["title"] == "John 3")

        # the chapter comes with where each verse is; its text has no reference markers
        ch = (await a.get(f"/api/chapters/{john3['id']}")).json()
        assert not MARKER.search(ch["text"])
        v16 = next(v for v in ch["verses"] if v["number"] == 16)
        assert ch["text"][v16["start"] : v16["stop"]].startswith("For God so loved the world")

        # references: with a book name, an abbreviation, a range, and "3:16" in the book on screen
        lookup = lambda ref, **kw: a.get(f"/api/books/{bid}/verses/lookup", params={"ref": ref, **kw})  # noqa: E731
        r = await lookup("John 3:16")
        assert r.status_code == 200 and (r.json()["chapter_id"], r.json()["verse"], r.json()["start"]) == (john3["id"], 16, v16["start"])
        r = await lookup("Gen 1:3-5")
        assert r.status_code == 200 and (r.json()["title"], r.json()["verse"], r.json()["verse_end"]) == ("Genesis 1", 3, 5)
        assert (await lookup("3:16", from_chapter=john3["id"])).json()["verse"] == 16
        assert (await lookup("3:16")).status_code == 422  # which book? there are four
        r = await lookup("Matt 17:21")
        assert r.status_code == 404 and "leaves it out" in r.json()["detail"]
        assert (await lookup("Exodus 1:1")).status_code == 404

        # read aloud: built from the verses, the chapter announced once, no markers
        items = (await a.get(f"/api/tts/chapters/{john3['id']}/sentences")).json()["sentences"]
        assert [(i["kind"], i["text"]) for i in items[:3]] == [
            ("chapter", "John, chapter 3."), ("verse-number", "Verse 1."), ("text", items[2]["text"])]
        assert [i["kind"] for i in items].count("chapter") == 1
        assert not [i["text"] for i in items if i["kind"] == "text" and MARKER.search(i["text"])]

        # passages carry their verses, and are cited by them
        hits = (await a.get(f"/api/books/{bid}/retrieve", params={"q": "God so loved the world", "k": 3})).json()
        top = next(h for h in hits if h["chapter_title"] == "John 3")
        assert top["verse_start"] <= 16 <= top["verse_end"]
        assert top["label"] == f"John 3:{top['verse_start']}–{top['verse_end']}"
        assert "3:16 For God so loved" in top["numbered_text"]

        # ownership: another reader's lookups, chapters and read-aloud items are 404
        assert (await b.get(f"/api/books/{bid}/verses/lookup", params={"ref": "John 3:16"})).status_code == 404
        assert (await b.get(f"/api/chapters/{john3['id']}")).status_code == 404
        assert (await b.get(f"/api/tts/chapters/{john3['id']}/sentences")).status_code == 404
        assert (await b.put(f"/api/books/{bid}/verse-mode", json={"detect": False})).status_code == 404

        # turning detection off re-indexes it as an ordinary book
        r = await a.put(f"/api/books/{bid}/verse-mode", json={"detect": False})
        assert r.status_code == 202, r.text
        plain = await _ready(a, bid)
        assert plain["verses"] is None and plain["verse_mode"] == "off"
        chapters = (await a.get(f"/api/books/{bid}/chapters")).json()
        assert all(c["number"] is None for c in chapters)
        assert (await lookup("John 3:16")).status_code == 400

        assert (await a.delete(f"/api/books/{bid}")).status_code == 204
