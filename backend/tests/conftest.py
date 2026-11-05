"""Test setup. Integration tests use a separate database: <your db name>_test.

It is created (with pgvector + migrations) automatically via scripts/setup_db.py.
Tests needing Postgres are skipped if the server can't be reached.
"""
from __future__ import annotations

import asyncio
import uuid
import os
import subprocess
import tempfile
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Point the app at the test database BEFORE anything imports app.config.
from dotenv import dotenv_values  # noqa: E402

_base = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND / ".env").get("DATABASE_URL", "")
if _base and not _base.rstrip("/").endswith("_test"):
    head, _, name = _base.rpartition("/")
    os.environ["DATABASE_URL"] = f"{head}/{name.split('?')[0]}_test"
os.environ.setdefault("RERANK_ENABLED", "true")
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="bookmind-test-uploads-")  # never the real library folder
os.environ["TTS_CACHE_DIR"] = tempfile.mkdtemp(prefix="bookmind-test-tts-cache-")  # nor the real audio cache
os.environ["BOOKMIND_ENV_OVERRIDE"] = "1"  # let these variables beat backend/.env (also in subprocesses)

_db_ready: bool | None = None


def _prepare_db() -> bool:
    global _db_ready
    if _db_ready is None:
        r = subprocess.run([sys.executable, "scripts/setup_db.py"], cwd=BACKEND, capture_output=True, text=True)
        _db_ready = r.returncode == 0
        if not _db_ready:
            print(r.stdout, r.stderr)
    return _db_ready


@pytest.fixture(scope="session")
def event_loop_policy():
    # psycopg's async driver needs a selector event loop on Windows.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def test_db():
    if not _prepare_db():
        pytest.skip("PostgreSQL test database unavailable (see output above)")
    return os.environ["DATABASE_URL"]


@asynccontextmanager
async def signed_in(app, email: str | None = None):
    """An API client signed in as a brand-new user, with the CSRF and app headers already set."""
    import httpx

    from app.auth import ratelimit

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60,
                                 headers={"X-Requested-With": "BookMind"}) as c:
        ratelimit.clear_all()  # many sign-ups from one "IP" in a test run
        email = email or f"reader-{uuid.uuid4().hex[:10]}@example.com"
        r = await c.post("/api/auth/signup", json={"email": email, "password": "correct horse battery",
                                                    "display_name": "Tester"})
        assert r.status_code == 201, r.text
        c.headers["X-CSRF-Token"] = c.cookies.get("bm_csrf", "")
        c.user = r.json()["user"]
        yield c
