"""End-to-end: upload -> background indexing -> hybrid retrieval API -> spoiler guard -> cascade delete.

Uses the real embedding/rerank models (downloaded on first run) and the _test database.
No LLM calls are made.
"""
from __future__ import annotations

import asyncio

import httpx

from tests.conftest import signed_in
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

BOOK = """Title: The Lighthouse Keeper
Author: Test Author

*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

CHAPTER I.
The Storm

{c1}

CHAPTER II.
The Key

{c2}

CHAPTER III.
The Secret

{c3}

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***
This license text must not be indexed.
"""

C1 = "\n\n".join([
    "Mara kept the lighthouse on the northern cliff. Every night she climbed the hundred stairs to light the great lamp.",
    "One autumn evening a violent storm rolled in from the sea, and the waves broke over the rocks like thunder.",
] * 6)
C2 = "\n\n".join([
    "In the morning Mara found a small brass key lying in the sand below the cliff, green with age.",
    "She wondered which door the brass key might open, and kept it in her apron pocket.",
] * 6)
C3 = "\n\n".join([
    "The brass key opened a hidden cellar beneath the lighthouse where her grandfather had stored his diaries.",
    "The diaries revealed that the lighthouse had once been used by smugglers carrying French brandy.",
] * 6)


async def _wait_ready(client: httpx.AsyncClient, book_id: int, timeout: float = 300) -> dict:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        b = (await client.get(f"/api/books/{book_id}")).json()
        if b["status"] in ("ready", "failed"):
            return b
        await asyncio.sleep(0.5)
    raise TimeoutError(f"indexing did not finish: last status {b['status']} {b['progress']:.0%} {b['status_message']!r}")


async def test_upload_index_retrieve_spoiler_delete(test_db, tmp_path):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with signed_in(app) as client:
        files = {"file": ("lighthouse.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")}
        r = await client.post("/api/books", files=files)
        assert r.status_code == 201, r.text
        book_id = r.json()["id"]

        book = await _wait_ready(client, book_id)
        assert book["status"] == "ready", book["error"]
        assert book["title"] == "The Lighthouse Keeper"
        assert book["chapter_count"] == 3

        chapters = (await client.get(f"/api/books/{book_id}/chapters")).json()
        titles = [c["title"] for c in chapters]
        assert len(titles) == 3
        for t, sub in zip(titles, ["The Storm", "The Key", "The Secret"]):
            assert t.startswith("CHAPTER") and sub in t, titles

        # Semantic question -> the smuggler passage in chapter 3.
        hits = (await client.get(f"/api/books/{book_id}/retrieve", params={"q": "who used the lighthouse for illegal trade?"})).json()
        assert hits, "no results"
        assert hits[0]["chapter_position"] == 3
        assert "smugglers" in hits[0]["text"]
        # Every hit is an exact slice of its chapter (needed for reader highlighting).
        ch = (await client.get(f"/api/chapters/{hits[0]['chapter_id']}")).json()
        assert ch["text"][hits[0]["char_start"]:hits[0]["char_end"]] == hits[0]["text"]
        assert all("license text" not in h["text"] for h in hits)

        # Keyword-heavy question works too.
        hits = (await client.get(f"/api/books/{book_id}/retrieve", params={"q": "brass key apron pocket"})).json()
        assert hits[0]["chapter_position"] == 2

        # Spoiler guard: nothing beyond chapter 1 is ever returned.
        guarded = (await client.get(f"/api/books/{book_id}/retrieve",
                                    params={"q": "smugglers French brandy diaries", "max_chapter": 1})).json()
        assert guarded and all(h["chapter_position"] <= 1 for h in guarded)

        # Reader search: exact, case-insensitive, with offsets into chapter text.
        found = (await client.get(f"/api/books/{book_id}/search", params={"q": "BRASS KEY"})).json()
        assert found["total"] >= 12
        r0 = found["results"][0]
        ch = (await client.get(f"/api/chapters/{r0['chapter_id']}")).json()
        assert ch["text"][r0["start"]:r0["end"]].lower() == "brass key"
        assert (await client.get(f"/api/books/{book_id}/search", params={"q": "100%_"})).json()["total"] == 0

        # Validation errors.
        assert (await client.post("/api/books", files={"file": ("x.exe", b"MZ", "application/octet-stream")})).status_code == 415
        assert (await client.post("/api/books", files={"file": ("empty.txt", b"", "text/plain")})).status_code == 400

        # Cascade delete removes chunks.
        chunk_id = hits[0]["chunk_id"]
        assert (await client.delete(f"/api/books/{book_id}")).status_code == 204
        assert (await client.get(f"/api/chunks/{chunk_id}")).status_code == 404
        assert (await client.get(f"/api/books/{book_id}")).status_code == 404
