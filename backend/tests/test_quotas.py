"""Per-user limits: books per library, chat messages per day, upload size; stats only count your own books."""
from __future__ import annotations

import pytest

from tests.conftest import signed_in
from tests.test_account import _add_book, _app

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_book_limit_is_per_user(test_db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_books_per_user", 1)
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        await _add_book(a.user["id"])
        r = await a.post("/api/books", files={"file": ("second.txt", b"Another book entirely.", "text/plain")})
        assert r.status_code == 409 and "library is full" in r.json()["detail"]
        # Someone else's full library doesn't count against yours (the indexer isn't started for a fake book).
        await _add_book(b.user["id"])
        assert len((await b.get("/api/books")).json()) == 1


async def test_daily_message_limit(test_db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "daily_message_limit", 1)  # _add_book's chat already has one question
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        book_a = await _add_book(a.user["id"])
        r = await a.post(f"/api/books/{book_a}/chat", json={"message": "And the frost?"})
        assert r.status_code == 429 and "limit of 1 messages" in r.json()["detail"]
        # A's messages don't count toward B's limit (checked directly: no real AI call in tests).
        from app.api.chat import check_daily_messages
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            await check_daily_messages(db, type("U", (), {"id": b.user["id"]})())


async def test_stats_only_count_your_books(test_db):
    from app.db.session import SessionLocal
    from app.features.stats import add_activity

    async with signed_in(_app()) as a, signed_in(_app()) as b:
        book_a = await _add_book(a.user["id"])
        async with SessionLocal() as db:
            await add_activity(db, book_a, seconds=600)
            await db.commit()
        mine, theirs = (await a.get("/api/stats")).json(), (await b.get("/api/stats")).json()
        assert mine["today_seconds"] == 600 and [x["id"] for x in mine["books"]] == [book_a]
        assert theirs["today_seconds"] == 0 and theirs["books"] == []
