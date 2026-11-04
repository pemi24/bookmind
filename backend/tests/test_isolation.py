"""Private libraries: one reader can never see, search, change or delete another reader's data."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from tests.conftest import signed_in

pytestmark = pytest.mark.asyncio(loop_scope="session")

BOOK = """Title: The Orchard Ledger
Author: Test Author

CHAPTER I. The Ledger

{body}

CHAPTER II. The Frost

The frost came early that year and the orchard keeper counted every damaged quince twice.
"""


async def _ready(c: httpx.AsyncClient, book_id: int, timeout: float = 300) -> dict:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        b = (await c.get(f"/api/books/{book_id}")).json()
        if b["status"] in ("ready", "failed"):
            return b
        await asyncio.sleep(0.5)
    raise TimeoutError("indexing did not finish")


async def test_readers_cannot_reach_each_others_data(test_db):
    from sqlalchemy import select

    from app.db.models import Conversation, Note
    from app.db.session import SessionLocal
    from app.main import app
    from app.retrieval.hybrid import search_books

    body = " ".join(["The orchard keeper wrote the quince harvest into a green ledger every autumn."] * 20)
    async with signed_in(app) as a, signed_in(app) as b:
        r = await a.post("/api/books", files={"file": ("orchard.txt", BOOK.format(body=body).encode(), "text/plain")})
        assert r.status_code == 201, r.text
        book = r.json()
        assert (await _ready(a, book["id"]))["status"] == "ready"
        bid = book["id"]
        chapter_id = (await a.get(f"/api/books/{bid}/chapters")).json()[0]["id"]
        chunk_id = (await a.get(f"/api/books/{bid}/retrieve", params={"q": "quince ledger"})).json()[0]["chunk_id"]
        note = (await a.post(f"/api/books/{bid}/notes", json={"kind": "note", "content": "mine"})).json()
        async with SessionLocal() as db:
            conv = Conversation(book_id=bid, book_ids=[bid], mode="default", title="A's chat")
            db.add(conv)
            await db.commit()
            conv_id, conv_owner = conv.id, conv.user_id
        assert conv_owner == a.user["id"]  # owner filled in from the book by the database

        # The file lives in the owner's own folder.
        async with SessionLocal() as db:
            from app.db.models import Book
            path = Path((await db.get(Book, bid)).file_path)
        assert path.parent.name == f"user-{a.user['id']}"

        # B sees an empty library and an empty history...
        assert (await b.get("/api/books")).json() == []
        assert (await b.get("/api/stats")).json()["books"] == []
        # ...and every one of A's resources is simply "not found" (never 403, which would confirm it exists).
        for method, url, kw in [
            ("GET", f"/api/books/{bid}", {}), ("GET", f"/api/books/{bid}/chapters", {}),
            ("GET", f"/api/chapters/{chapter_id}", {}), ("GET", f"/api/chunks/{chunk_id}", {}),
            ("GET", f"/api/books/{bid}/retrieve", {"params": {"q": "quince"}}),
            ("GET", f"/api/books/{bid}/search", {"params": {"q": "quince"}}),
            ("POST", f"/api/books/{bid}/chat", {"json": {"message": "what is in the ledger?"}}),
            ("GET", f"/api/books/{bid}/conversations", {}), ("GET", f"/api/conversations/{conv_id}", {}),
            ("PATCH", f"/api/conversations/{conv_id}", {"json": {"title": "stolen"}}),
            ("DELETE", f"/api/conversations/{conv_id}", {}),
            ("GET", f"/api/books/{bid}/notes", {}), ("POST", f"/api/books/{bid}/notes", {"json": {"kind": "note", "content": "x"}}),
            ("PATCH", f"/api/notes/{note['id']}", {"json": {"content": "changed"}}),
            ("DELETE", f"/api/notes/{note['id']}", {}),
            ("GET", f"/api/books/{bid}/quizzes", {}), ("GET", f"/api/books/{bid}/flashcards", {}),
            ("GET", f"/api/books/{bid}/memory", {}), ("GET", f"/api/books/{bid}/jobs/memory", {}),
            ("GET", f"/api/books/{bid}/entities", {}), ("GET", f"/api/chapters/{chapter_id}/translation", {"params": {"language": "French"}}),
            ("PUT", f"/api/books/{bid}/reading", {"json": {"position": 1}}),
            ("POST", f"/api/books/{bid}/reindex", {}), ("DELETE", f"/api/books/{bid}", {}),
        ]:
            r = await b.request(method, url, **kw)
            assert r.status_code == 404, (method, url, r.status_code, r.text)

        # Library-wide search ignores other readers' books, even when asked for them by id.
        r = await b.post("/api/library/search", json={"q": "quince ledger", "book_ids": [bid]})
        assert r.status_code == 409
        # And the restriction is in the SQL itself, not a later filter.
        async with SessionLocal() as db:
            assert await search_books(db, "quince ledger", [bid], {}, user_id=b.user["id"]) == []
            assert await search_books(db, "quince ledger", [bid], {}, user_id=a.user["id"])

        # Nothing of A's was changed by B's attempts.
        assert (await a.get(f"/api/books/{bid}")).status_code == 200
        assert (await a.get(f"/api/conversations/{conv_id}")).json()["title"] == "A's chat"
        # The owner can rename their chat.
        r = await a.patch(f"/api/conversations/{conv_id}", json={"title": "  Ledger questions  "})
        assert r.status_code == 200 and r.json()["title"] == "Ledger questions"
        assert [c["title"] for c in (await a.get(f"/api/books/{bid}/conversations")).json()] == ["Ledger questions"]
        notes = (await a.get(f"/api/books/{bid}/notes")).json()["notes"]
        assert [n["content"] for n in notes] == ["mine"]

        # The database refuses a row whose owner doesn't match its book's owner.
        async with SessionLocal() as db:
            db.add(Note(book_id=bid, user_id=b.user["id"], kind="note", content="sneaky"))
            with pytest.raises(Exception, match="belongs to user"):
                await db.commit()

        # A deleting their book removes it (and its file).
        assert (await a.delete(f"/api/books/{bid}")).status_code == 204
        async with SessionLocal() as db:
            assert (await db.scalar(select(Conversation).where(Conversation.id == conv_id))) is None


async def test_signed_out_requests_are_refused(test_db):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        for url in ("/api/books", "/api/stats", "/api/network", "/api/books/1/chapters", "/api/conversations/1"):
            assert (await c.get(url)).status_code == 401, url
        assert (await c.get("/api/health")).status_code == 200


async def test_csrf_token_required_for_changes(test_db):
    from app.main import app

    async with signed_in(app) as c:
        del c.headers["X-CSRF-Token"]
        r = await c.post("/api/books", files={"file": ("x.txt", b"hello there", "text/plain")})
        assert r.status_code == 403
        assert (await c.get("/api/books")).status_code == 200  # reads don't need it
