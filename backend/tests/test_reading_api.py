"""Reader highlights (colour, comment, per-chapter lookup) and server-side reading progress."""
from __future__ import annotations

import httpx
import pytest

from tests.test_features_api import fake_llm  # noqa: F401  (fixture)
from tests.test_retrieval_api import BOOK, C1, C2, C3, _wait_ready

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_highlights_and_reading_progress(test_db, fake_llm):  # noqa: F811
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        r = await c.post("/api/books", files={"file": ("rd.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        try:
            assert (await _wait_ready(c, book_id))["status"] == "ready"
            chapters = (await c.get(f"/api/books/{book_id}/chapters")).json()
            ch1, ch2 = chapters[0]["id"], chapters[1]["id"]

            # --- highlights
            loc = {"chapter_id": ch1, "chapter_title": "One", "page": 1, "char_start": 10, "char_end": 40}
            h = (await c.post(f"/api/books/{book_id}/notes", json={
                "kind": "passage", "content": "some text", "location": loc, "color": "green", "comment": "  Nice line  ",
            })).json()
            assert h["color"] == "green" and h["comment"] == "Nice line"
            await c.post(f"/api/books/{book_id}/notes", json={"kind": "note", "content": "No location"})
            await c.post(f"/api/books/{book_id}/notes", json={
                "kind": "passage", "content": "other chapter", "location": {**loc, "chapter_id": ch2}})
            bad = await c.post(f"/api/books/{book_id}/notes", json={"kind": "passage", "content": "x", "color": "purple"})
            assert bad.status_code == 422

            hl = (await c.get(f"/api/books/{book_id}/highlights", params={"chapter_id": ch1})).json()
            assert [n["id"] for n in hl] == [h["id"]]  # plain notes and other chapters are left out

            upd = (await c.patch(f"/api/notes/{h['id']}", json={"color": "pink", "comment": ""})).json()
            assert upd["color"] == "pink" and upd["comment"] is None
            await c.patch(f"/api/notes/{h['id']}", json={"comment": "Remember this"})
            md = (await c.get(f"/api/books/{book_id}/notes/export", params={"format": "md"})).text
            assert "Remember this" in md

            # --- reading progress
            assert (await c.get(f"/api/books/{book_id}")).json()["reading"] is None
            rd = (await c.put(f"/api/books/{book_id}/reading", json={"position": 2, "offset": 120, "reached": True})).json()
            assert rd["position"] == 2 and rd["offset"] == 120 and rd["furthest"] == 2
            # Jumping back (or peeking ahead without reading) never lowers / raises the furthest chapter.
            rd = (await c.put(f"/api/books/{book_id}/reading", json={"position": 1, "offset": 0, "reached": True})).json()
            assert rd["position"] == 1 and rd["furthest"] == 2
            rd = (await c.put(f"/api/books/{book_id}/reading", json={"position": 3, "offset": 0})).json()
            assert rd["position"] == 3 and rd["furthest"] == 2
            assert (await c.get(f"/api/books/{book_id}")).json()["reading"]["position"] == 3
            assert (await c.put(f"/api/books/{book_id}/reading", json={"position": 99})).status_code == 400

            assert (await c.delete(f"/api/books/{book_id}/reading")).status_code == 204
            assert (await c.get(f"/api/books/{book_id}")).json()["reading"] is None
        finally:
            await c.delete(f"/api/books/{book_id}")
