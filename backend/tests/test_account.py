"""Settings (profile, email, password, preferences, devices), export, delete account, admin."""
from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest

from tests.conftest import signed_in

pytestmark = pytest.mark.asyncio(loop_scope="session")
PASSWORD = "correct horse battery"  # what signed_in() signs up with


def _app():
    from app.main import app

    return app


async def _sign_in(email: str, password: str = PASSWORD) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test",
                          headers={"X-Requested-With": "BookMind"})
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("bm_csrf", "")
    return c


async def _make_admin(user_id: int, admin: bool = True) -> None:
    from app.db.models import User
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        (await db.get(User, user_id)).is_admin = admin
        await db.commit()


async def test_profile_and_preferences(test_db, monkeypatch):
    from app.config import get_settings

    async with signed_in(_app()) as c:
        r = await c.patch("/api/account/profile", json={"display_name": "  Ada   Lovelace "})
        assert r.json()["user"]["display_name"] == "Ada Lovelace"
        r = await c.patch("/api/account/preferences", json={"theme": "dark"})
        assert r.json()["user"]["settings"]["theme"] == "dark"
        assert (await c.patch("/api/account/preferences", json={"theme": "purple"})).status_code == 422
        assert (await c.patch("/api/account/preferences", json={"llm_provider": "skynet"})).status_code == 422
        monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
        r = await c.patch("/api/account/preferences", json={"llm_provider": "anthropic"})
        assert r.status_code == 422 and "no API key" in r.json()["detail"]

        monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
        options = (await c.get("/api/account/ai-options")).json()
        assert "groq" in [p["name"] for p in options["providers"]]
        r = await c.patch("/api/account/preferences", json={"llm_provider": "groq", "llm_model": "some/model-1"})
        prefs = r.json()["user"]["settings"]
        assert (prefs["llm_provider"], prefs["llm_model"]) == ("groq", "some/model-1")
        assert (await c.patch("/api/account/preferences", json={"llm_model": "bad model; drop"})).status_code == 422
        # Back to the server's default clears the model too.
        r = await c.patch("/api/account/preferences", json={"llm_provider": ""})
        assert r.json()["user"]["settings"]["llm_model"] == ""


async def test_users_choice_of_ai_is_used_for_their_requests(test_db, monkeypatch):
    from app.config import get_settings
    from app.llm.providers import choice_from_settings, current_provider, get_provider, user_choice

    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    assert choice_from_settings({}) is None and choice_from_settings({"llm_provider": "nope"}) is None
    token = user_choice.set(choice_from_settings({"llm_provider": "groq", "llm_model": "some/model-1"}))
    try:
        p = current_provider()
        assert p.name == "groq" and p.model == "some/model-1"
    finally:
        user_choice.reset(token)
    assert current_provider() is get_provider()


async def test_change_password_signs_out_other_devices(test_db):
    async with signed_in(_app()) as c:
        email = c.user["email"]
        other = await _sign_in(email)
        assert (await c.post("/api/account/password", json={"current_password": "nope nope nope",
                                                              "new_password": "a whole new phrase"})).status_code == 403
        assert (await c.post("/api/account/password", json={"current_password": PASSWORD,
                                                              "new_password": "short"})).status_code == 422
        r = await c.post("/api/account/password", json={"current_password": PASSWORD, "new_password": "a whole new phrase"})
        assert r.status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 200  # this device stays signed in
        assert (await other.get("/api/auth/me")).status_code == 401
        await other.aclose()
        bad = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert bad.status_code == 401
        await (await _sign_in(email, "a whole new phrase")).aclose()


async def test_change_email(test_db):
    from app.auth import mailer

    async with signed_in(_app()) as a, signed_in(_app()) as b:
        old = a.user["email"]
        new = "renamed-" + old
        assert (await a.post("/api/account/email", json={"email": new, "password": "wrong one!"})).status_code == 403
        assert (await a.post("/api/account/email", json={"email": b.user["email"], "password": PASSWORD})).status_code == 409
        assert (await a.post("/api/account/email", json={"email": "not-an-email", "password": PASSWORD})).status_code == 422
        r = await a.post("/api/account/email", json={"email": new.upper(), "password": PASSWORD})
        assert r.status_code == 200 and r.json()["user"]["email"] == new
        assert any(m["to"] == old and "changed" in m["subject"] for m in mailer.sent)  # the old address is told
        c2 = await _sign_in(new)
        await c2.aclose()


async def test_devices_list_and_sign_out_one(test_db):
    async with signed_in(_app()) as c:
        other = await _sign_in(c.user["email"])
        devices = (await c.get("/api/account/sessions")).json()
        assert len(devices) == 2 and sum(d["current"] for d in devices) == 1
        theirs = next(d for d in devices if not d["current"])
        mine = next(d for d in devices if d["current"])
        assert (await c.delete(f"/api/account/sessions/{mine['id']}")).status_code == 400
        assert (await c.delete(f"/api/account/sessions/{theirs['id']}")).status_code == 204
        assert (await other.get("/api/auth/me")).status_code == 401
        await other.aclose()
        # Someone else's device can't be ended (or even confirmed to exist).
        async with signed_in(_app()) as stranger:
            assert (await stranger.delete(f"/api/account/sessions/{mine['id']}")).status_code == 404


async def _add_book(user_id: int, title: str = "The Orchard Ledger") -> int:
    """A book row with a file and some notes/chats, without running the indexer."""
    from app.api.books import user_upload_dir
    from app.db.models import Book, Conversation, Message, Note
    from app.db.session import SessionLocal

    path = user_upload_dir(user_id) / "orchard.txt"
    path.write_text("The orchard keeper wrote the quince harvest into a green ledger.", encoding="utf-8")
    async with SessionLocal() as db:
        b = Book(user_id=user_id, title=title, filename="orchard.txt", file_path=str(path), file_type="txt",
                 file_size=path.stat().st_size, status="ready", warnings=[], suggested_questions=[])
        db.add(b)
        await db.flush()
        db.add(Note(book_id=b.id, kind="note", content="Remember the green ledger."))
        conv = Conversation(book_id=b.id, book_ids=[b.id], mode="chat", title="About the ledger")
        db.add(conv)
        await db.flush()
        db.add_all([Message(conversation_id=conv.id, role="user", content="What colour is the ledger?", meta={}),
                    Message(conversation_id=conv.id, role="assistant", content="Green [1].",
                            meta={"sources": [{"marker": 1, "chapter_title": "One", "text": "a green ledger"}]})])
        await db.commit()
        return b.id


async def test_export_contains_everything_and_only_mine(test_db):
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        await _add_book(a.user["id"])
        await _add_book(b.user["id"], title="Someone Else's Diary")
        r = await a.get("/api/account/export")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        assert "account.json" in names and "README.txt" in names
        assert "password_hash" not in z.read("account.json").decode()
        folder = next(n.rsplit("/", 1)[0] for n in names if n.endswith("/book.json"))
        assert "orchard-ledger" in folder
        assert {f"{folder}/orchard.txt", f"{folder}/notes.md", f"{folder}/chats.json"} <= set(names)
        chats = json.loads(z.read(f"{folder}/chats.json"))
        assert chats[0]["messages"][1]["sources"][0]["text"] == "a green ledger"
        assert not any("diary" in n for n in names)


async def test_delete_account_removes_everything(test_db):
    from sqlalchemy import select

    from app.api.books import user_upload_dir
    from app.db.models import Book, User
    from app.db.session import SessionLocal

    async with signed_in(_app()) as c:
        uid, email = c.user["id"], c.user["email"]
        book_id = await _add_book(uid)
        folder = user_upload_dir(uid)
        assert (await c.post("/api/account/delete", json={"password": "wrong one!"})).status_code == 403
        r = await c.post("/api/account/delete", json={"password": PASSWORD})
        assert r.status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 401
        assert not folder.exists()
        async with SessionLocal() as db:
            assert await db.get(User, uid) is None
            assert await db.scalar(select(Book).where(Book.id == book_id)) is None
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 401


async def test_only_admin_cannot_delete_their_account(test_db):
    from sqlalchemy import update

    from app.db.models import User
    from app.db.session import SessionLocal

    async with signed_in(_app()) as c:
        async with SessionLocal() as db:  # this test's user is the only active admin for a moment
            await db.execute(update(User).where(User.is_admin).values(is_active=False))
            await db.commit()
        try:
            await _make_admin(c.user["id"])
            r = await c.post("/api/account/delete", json={"password": PASSWORD})
            assert r.status_code == 409 and "only admin" in r.json()["detail"]
        finally:
            async with SessionLocal() as db:
                await db.execute(update(User).where(User.is_admin).values(is_active=True))
                await db.commit()
            await _make_admin(c.user["id"], False)


async def test_admin_page(test_db):
    async with signed_in(_app()) as admin, signed_in(_app()) as reader:
        # Not an admin: the admin API doesn't exist for you.
        assert (await reader.get("/api/admin/users")).status_code == 404
        await _make_admin(admin.user["id"])
        await _add_book(reader.user["id"])
        users = {u["id"]: u for u in (await admin.get("/api/admin/users")).json()}
        row = users[reader.user["id"]]
        assert row["books"] == 1 and row["chats"] == 1 and row["storage_bytes"] > 0
        assert not {"password_hash", "settings", "title", "content"} & set(row)
        # Admins can't look into a reader's books.
        book = (await reader.get("/api/books")).json()[0]
        assert (await admin.get(f"/api/books/{book['id']}")).status_code == 404

        assert (await admin.patch(f"/api/admin/users/{admin.user['id']}", json={"is_admin": False})).status_code == 400
        r = await admin.patch(f"/api/admin/users/{reader.user['id']}", json={"is_active": False})
        assert r.json()["is_active"] is False
        assert (await reader.get("/api/books")).status_code == 401  # suspended: signed out at once
        login = await reader.post("/api/auth/login", json={"email": reader.user["email"], "password": PASSWORD})
        assert login.status_code == 401
        assert (await admin.delete(f"/api/admin/users/{reader.user['id']}")).status_code == 204
        assert reader.user["id"] not in {u["id"] for u in (await admin.get("/api/admin/users")).json()}
        await _make_admin(admin.user["id"], False)


async def test_ai_choice_reaches_the_endpoint_and_streamed_answers(test_db, monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.responses import StreamingResponse

    from app.auth.deps import current_user
    from app.config import get_settings
    from app.llm.client import provider

    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    probe = FastAPI()

    @probe.get("/now", dependencies=[Depends(current_user)])
    async def now():
        return {"provider": provider().name}

    @probe.get("/stream", dependencies=[Depends(current_user)])
    async def stream():
        async def gen():
            yield provider().name  # runs after the endpoint returned, like chat answers
        return StreamingResponse(gen())

    async with signed_in(_app()) as c:
        await c.patch("/api/account/preferences", json={"llm_provider": "groq"})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=probe), base_url="http://test",
                                     cookies=c.cookies) as p:
            assert (await p.get("/now")).json()["provider"] == "groq"
            assert (await p.get("/stream")).text == "groq"
