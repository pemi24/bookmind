"""Graceful failure: bad files, huge files, database down, AI model unreachable.

Each case must end in a clear, user-facing message, never a crash or a hang.
"""
from __future__ import annotations

import json

import httpx

from tests.conftest import signed_in
import psycopg
import pytest

from tests.test_retrieval_api import BOOK, C1, C2, C3, _wait_ready


@pytest.fixture
async def client(test_db):
    from app.main import app

    async with signed_in(app) as c:
        yield c


async def _upload(client, name: str, data: bytes, mime: str = "application/octet-stream") -> dict:
    r = await client.post("/api/books", files={"file": (name, data, mime)})
    assert r.status_code == 201, r.text
    return r.json()


async def test_corrupt_pdf_fails_with_clear_message(client):
    book = await _upload(client, "broken.pdf", b"%PDF-1.4\nthis is not really a pdf", "application/pdf")
    done = await _wait_ready(client, book["id"], timeout=120)
    assert done["status"] == "failed"
    assert "could not be opened" in done["error"] or "corrupted" in done["error"]
    await client.delete(f"/api/books/{book['id']}")


async def test_scanned_pdf_without_ocr_explains_what_to_do(client, monkeypatch):
    import pymupdf

    from app.ingestion.parsers import pdf as pdf_parser

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: False)
    doc = pymupdf.open()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), 0)
    pix.clear_with(200)
    for _ in range(3):  # image-only pages: no text layer at all
        doc.new_page().insert_image(pymupdf.Rect(50, 50, 300, 300), pixmap=pix)
    book = await _upload(client, "scan.pdf", doc.tobytes(), "application/pdf")
    done = await _wait_ready(client, book["id"], timeout=120)
    assert done["status"] == "failed"
    assert "scanned" in done["error"] and "Tesseract" in done["error"]
    await client.delete(f"/api/books/{book['id']}")


async def test_huge_upload_is_rejected_and_not_kept(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    before = {p for p in settings.upload_dir.rglob("*") if p.is_file()}
    r = await client.post("/api/books", files={"file": ("big.txt", b"x" * (2 * 1024 * 1024), "text/plain")})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
    assert {p for p in settings.upload_dir.rglob("*") if p.is_file()} == before  # partial file cleaned up


async def test_database_down_returns_503_with_hint(client):
    from app.db.session import get_db
    from app.main import app

    async def broken_db():
        raise psycopg.OperationalError("connection refused")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        r = await client.get("/api/books")
    finally:
        app.dependency_overrides.pop(get_db)
    assert r.status_code == 503
    assert "PostgreSQL" in r.json()["detail"]


async def test_llm_unreachable_gives_clear_chat_error_and_health_status(client, monkeypatch):
    import app.main as main
    from app.api import chat
    from app.config import get_settings
    from app.llm import client as llm
    from app.llm.providers.ollama import OllamaProvider

    book = await _upload(client, "lh.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")
    assert (await _wait_ready(client, book["id"]))["status"] == "ready"

    # A provider whose connections are refused. Refused at once rather than by a real closed port:
    # on Windows each refused connection to a local port takes ~2 s, and a chat makes several.
    def refuse(request: httpx.Request):
        raise httpx.ConnectError("connection refused", request=request)

    dead = OllamaProvider(get_settings().model_copy(update={"ollama_host": "http://127.0.0.1:9"}),
                          transport=httpx.MockTransport(refuse))
    monkeypatch.setattr(llm, "current_provider", lambda: dead)
    monkeypatch.setattr(main, "_llm_cache", {"at": 0.0, "status": None})

    r = await client.post(f"/api/books/{book['id']}/chat", json={"message": "Where is the brass key?"})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    errors = [e["message"] for e in events if "message" in e and "partial" in e]
    assert errors and "Ollama isn't running" in errors[0] and "ollama.com/download" in errors[0]
    assert any("sources" in e for e in events)  # retrieval still worked before the model call

    health = (await client.get("/api/health")).json()
    assert health["llm"]["ready"] is False and "Ollama isn't running" in health["llm"]["message"]
    assert chat  # module imported: chat resolves the provider through app.llm.client at call time
    await client.delete(f"/api/books/{book['id']}")
