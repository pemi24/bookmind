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

            # --- Kindle import
            from tests.test_features_unit import CLIPPINGS
            f = {"file": ("My Clippings.txt", CLIPPINGS.encode("utf-8"), "text/plain")}
            prev = (await c.post(f"/api/books/{book_id}/kindle/preview", files=f)).json()["books"]
            assert prev[0]["title"] == "The Lighthouse Keeper: A Novel"
            res = (await c.post(f"/api/books/{book_id}/kindle/import", files=f,
                                data={"kindle_title": prev[0]["title"]})).json()
            assert res == {"imported": 1, "located": 1, "duplicates": 0, "notes_attached": 1, "standalone_notes": 0}
            hl = (await c.get(f"/api/books/{book_id}/highlights", params={"chapter_id": ch2})).json()
            kin = next(n for n in hl if "kindle" in n["tags"])
            assert kin["comment"] == "Where does the key come from?" and kin["location"]["char_end"] > kin["location"]["char_start"]
            again = (await c.post(f"/api/books/{book_id}/kindle/import", files=f,
                                  data={"kindle_title": prev[0]["title"]})).json()
            assert again["imported"] == 0 and again["duplicates"] == 1  # importing twice adds nothing
            bad = await c.post(f"/api/books/{book_id}/kindle/preview",
                               files={"file": ("x.txt", b"just some text", "text/plain")})
            assert bad.status_code == 400
        finally:
            await c.delete(f"/api/books/{book_id}")


async def test_library_essay_translation_stats(test_db, fake_llm):  # noqa: F811
    import asyncio
    import json

    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        r = await c.post("/api/books", files={"file": ("lib.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        try:
            assert (await _wait_ready(c, book_id))["status"] == "ready"
            chapters = (await c.get(f"/api/books/{book_id}/chapters")).json()

            # --- whole-library search, with this book's spoiler limit applied
            res = (await c.post("/api/library/search", json={
                "q": "brandy smugglers diaries", "book_ids": [book_id], "max_chapters": {str(book_id): 3}})).json()
            assert res["results"] and res["results"][0]["chapter_position"] == 3
            guarded = (await c.post("/api/library/search", json={
                "q": "brandy smugglers diaries", "book_ids": [book_id], "max_chapters": {str(book_id): 1}})).json()
            assert all(s["chapter_position"] <= 1 for s in guarded["results"])
            ask = await c.post("/api/library/ask", json={"q": "What was in the cellar?", "book_ids": [book_id]})
            events = [json.loads(line[6:]) for line in ask.text.splitlines() if line.startswith("data: ")]
            assert any("sources" in e for e in events) and any("cited" in e for e in events)

            # --- essay helper: real quotes kept (with location), invented ones dropped
            essay = (await c.post(f"/api/books/{book_id}/essay", json={"thesis": "The lighthouse hides its past."})).json()
            ev = essay["sections"][0]["evidence"]
            assert len(ev) == 1 and essay["dropped_quotes"] == 1 and ev[0]["char_end"] > ev[0]["char_start"]
            md = await c.post(f"/api/books/{book_id}/essay/export", json={"essay": essay})
            assert md.status_code == 200 and "**Thesis:**" in md.text and ev[0]["quote"] in md.text

            # --- translation: background job, then aligned paragraphs, then cached
            ch1 = chapters[0]["id"]
            start = (await c.post(f"/api/chapters/{ch1}/translation", json={"language": "French"})).json()
            assert start["status"] in ("running", "done")
            for _ in range(120):
                state = (await c.get(f"/api/chapters/{ch1}/translation", params={"language": "French"})).json()
                if state["status"] in ("done", "failed"):
                    break
                await asyncio.sleep(0.25)
            assert state["status"] == "done", state
            text = (await c.get(f"/api/chapters/{ch1}")).json()["text"]
            assert len(state["paragraphs"]) == len(text.split("\n\n"))
            assert all(p.startswith("FR: ") for p in state["paragraphs"] if sum(ch.isalpha() for ch in p) >= 2)
            again = (await c.post(f"/api/chapters/{ch1}/translation", json={"language": "French"})).json()
            assert again["status"] == "done"  # cached, no new job
            bad = await c.get(f"/api/chapters/{ch1}/translation", params={"language": "<script>"})
            assert bad.status_code == 400

            # --- stats: reading time and card reviews add up per day
            await c.post(f"/api/books/{book_id}/reading/time", json={"seconds": 45})
            await c.post(f"/api/books/{book_id}/reading/time", json={"seconds": 30})
            assert (await c.post(f"/api/books/{book_id}/reading/time", json={"seconds": 9999})).status_code == 422
            cards = (await c.post(f"/api/books/{book_id}/flashcards", json={"count": 3})).json()
            await c.post(f"/api/flashcards/{cards[0]['id']}/review", json={"grade": "good"})
            st = (await c.get("/api/stats")).json()
            mine = next(b for b in st["books"] if b["id"] == book_id)
            assert mine["seconds"] == 75 and st["today_seconds"] >= 75 and st["daily"][-1]["cards"] >= 1
            assert st["streak_days"] >= 1 and len(st["daily"]) == 30
        finally:
            await c.delete(f"/api/books/{book_id}")


async def test_chat_searches_again_before_saying_not_found(test_db, fake_llm, monkeypatch):  # noqa: F811
    import json

    from app.llm import client
    from app.llm.prompts import query as qp
    from app.main import app

    calls = {"stream": 0, "expand": 0}

    async def stream_text(system, messages, **kw):
        calls["stream"] += 1
        assert '"The Lighthouse Keeper"' in system  # the book overview is in the prompt
        if calls["stream"] == 1:
            yield "The provided passages do not state that."
        else:
            yield "The diaries tell of smugglers [1]."

    real_json = client.complete_json

    async def complete_json(system, user, schema, **kw):
        if schema is qp.ExpandOut:
            calls["expand"] += 1
            return qp.ExpandOut(queries=["smugglers French brandy", "grandfather diaries cellar"])
        return await real_json(system, user, schema, **kw)

    monkeypatch.setattr(client, "stream_text", stream_text)
    monkeypatch.setattr(client, "complete_json", complete_json)

    # The test book has only a few passages; let the first search miss most of them, as a real one can.
    from app.api import chat as chat_api

    real_search = chat_api.search_book
    searches = {"n": 0}

    async def search_book(*a, **kw):
        searches["n"] += 1
        found = await real_search(*a, **kw)
        return found[:1] if searches["n"] == 1 else found

    monkeypatch.setattr(chat_api, "search_book", search_book)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        r = await c.post("/api/books", files={"file": ("sa.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        try:
            assert (await _wait_ready(c, book_id))["status"] == "ready"
            resp = await c.post(f"/api/books/{book_id}/chat", json={"message": "Who used the lighthouse?"})
            events, ev = [], None
            for line in resp.text.splitlines():
                if line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: "):
                    events.append((ev, json.loads(line[6:])))
            kinds = [e for e, _ in events]
            assert "reset" in kinds and kinds.count("sources") == 2 and calls == {"stream": 2, "expand": 1}
            assert ("status", {"stage": "searching_more"}) in events
            done = next(d for e, d in events if e == "done")
            assert done["cited"] == [1]
            conv = next(d for e, d in events if e == "conversation")
            saved = (await c.get(f"/api/conversations/{conv['id']}")).json()["messages"]
            assert saved[-1]["content"] == "The diaries tell of smugglers [1]."  # the replaced answer is what's kept
        finally:
            await c.delete(f"/api/books/{book_id}")


async def test_book_memory_is_built_and_used_in_chat(test_db, fake_llm, monkeypatch):  # noqa: F811
    import asyncio

    from app.llm import client
    from app.main import app

    systems = []

    async def stream_text(system, messages, **kw):
        systems.append(system)
        yield "Mara keeps the lighthouse [1]."

    monkeypatch.setattr(client, "stream_text", stream_text)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        r = await c.post("/api/books", files={"file": ("mem.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        try:
            assert (await _wait_ready(c, book_id))["status"] == "ready"
            for _ in range(240):  # the memory job starts on its own after indexing
                st = (await c.get(f"/api/books/{book_id}/memory")).json()
                if st["chapters"] and st["done"] == st["chapters"]:
                    break
                await asyncio.sleep(0.25)
            assert st["done"] == st["chapters"] == 3, st
            again = (await c.post(f"/api/books/{book_id}/memory")).json()
            assert again["done"] == 3  # nothing left to write

            await c.post(f"/api/books/{book_id}/chat", json={"message": "Who keeps the lighthouse?"})
            assert "Chapter by chapter:" in systems[-1] and "SUMMARY" in systems[-1]  # the fake model's summaries
            await c.post(f"/api/books/{book_id}/chat", json={"message": "Who keeps the lighthouse?", "spoiler_chapter": 1})
            lines = [ln for ln in systems[-1].splitlines() if ln[:3] in ("1. ", "2. ", "3. ")]
            assert len(lines) == 1  # spoiler guard: only chapter 1's memory
        finally:
            await c.delete(f"/api/books/{book_id}")
