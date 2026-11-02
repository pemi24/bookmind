"""Test setup. Integration tests use a separate database: <your db name>_test.

It is created (with pgvector + migrations) automatically via scripts/setup_db.py.
Tests needing Postgres are skipped if the server can't be reached.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
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
