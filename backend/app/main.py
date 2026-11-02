"""FastAPI application: routers, startup checks, error handling."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from app.api import books, chat, features, notes, study
from app.config import get_settings
from app.db.models import AppMeta, Book
from app.db.session import SessionLocal
from app.features.jobs import fail_interrupted_jobs
from app.ingestion.parsers.pdf import tesseract_available
from app.llm.client import LLMError, provider, provider_status
from app.llm.providers import ProviderStatus
from app.retrieval.embeddings import get_embedder
from app.retrieval.rerank import get_reranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bookmind")

state: dict = {"db_ok": False, "db_error": None, "models_ready": False}
_llm_cache: dict = {"at": 0.0, "status": None}


async def _llm_status(max_age: float = 10.0) -> ProviderStatus:
    """Provider reachability (e.g. Ollama running + model pulled), cached briefly."""
    loop = asyncio.get_running_loop()
    if _llm_cache["status"] is None or loop.time() - _llm_cache["at"] > max_age:
        try:
            _llm_cache["status"] = await provider_status()
        except LLMError as e:
            _llm_cache["status"] = ProviderStatus(False, e.message)
        _llm_cache["at"] = loop.time()
    return _llm_cache["status"]


async def _startup_checks() -> None:
    s = get_settings()
    try:
        async with SessionLocal() as db:
            await db.execute(text("select 1"))
            row = await db.get(AppMeta, "embedding_dim")
            if row and int(row.value) != s.embedding_dim:
                raise RuntimeError(
                    f"Database was migrated with EMBEDDING_DIM={row.value} but .env says {s.embedding_dim}. "
                    "Use the original value, or create a fresh database."
                )
            # Indexing jobs don't survive a restart: mark them so the user can re-index.
            await db.execute(
                update(Book).where(Book.status.in_(["processing", "pending"]))
                .values(status="failed", error="Indexing was interrupted (server restarted). Click Re-index.",
                        status_message="Interrupted")
            )
            await db.commit()
        await fail_interrupted_jobs()
        state.update(db_ok=True, db_error=None)
    except ProgrammingError as e:
        state.update(db_ok=False, db_error="Database tables are missing. Run: python scripts/setup_db.py")
        log.error("%s (%s)", state["db_error"], e.orig)
    except Exception as e:  # noqa: BLE001
        state.update(db_ok=False, db_error=f"Cannot use the database: {e}")
        log.error(state["db_error"])


def _warm_models() -> None:
    """Load embedding + rerank models in the background so the first question is fast."""
    try:
        get_embedder().embed_query("warm up")
        rr = get_reranker()
        if rr:
            rr.score("warm up", ["warm up"])
        state["models_ready"] = True
        log.info("Embedding and re-ranking models loaded.")
    except Exception as e:  # noqa: BLE001
        state["models_error"] = str(e)
        log.error("Could not load models: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _startup_checks()
    status = await _llm_status(max_age=0)
    p = provider()
    if status.ok:
        log.info("LLM ready: %s", status.message)
    else:
        log.warning("=" * 70)
        log.warning("LLM provider '%s' (model %s) is NOT ready:", p.name, p.model)
        log.warning("  %s", status.message)
        log.warning("Books can still be uploaded, indexed, read and searched; chat and AI features")
        log.warning("will work once this is fixed (no restart needed for Ollama).")
        log.warning("=" * 70)
    warm = asyncio.create_task(asyncio.to_thread(_warm_models))
    yield
    warm.cancel()
    await p.aclose()


app = FastAPI(title="BookMind API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (books, chat, features, study, notes):
    app.include_router(module.router)


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


@app.exception_handler(OperationalError)
@app.exception_handler(DBAPIError)
@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(ConnectionRefusedError)
async def db_error_handler(_: Request, exc: Exception):
    log.error("Database error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable. Is PostgreSQL running? (see README > Troubleshooting)"},
    )


@app.get("/api/health")
async def health():
    s = get_settings()
    db_ok, db_msg, pgvector = False, state.get("db_error"), None
    try:
        async with SessionLocal() as db:
            pgvector = await db.scalar(text("select extversion from pg_extension where extname='vector'"))
            await db.scalar(select(AppMeta.value).limit(1))
            db_ok, db_msg = True, None
    except ProgrammingError:
        db_msg = "Database tables are missing. Run: python scripts/setup_db.py"
    except Exception as e:  # noqa: BLE001
        db_msg = f"Database unavailable: {e.__class__.__name__}. Is PostgreSQL running?"
    p = provider()
    llm_status = await _llm_status()
    return {
        "ok": db_ok and llm_status.ok,
        "database": {"ok": db_ok, "error": db_msg, "pgvector": pgvector},
        "llm": {"provider": p.name, "model": p.model, "local": p.local, "configured": p.configured(),
                "ready": llm_status.ok, "message": llm_status.message},
        "embeddings": {"model": s.embedding_model, "dim": s.embedding_dim, "loaded": state["models_ready"],
                       "error": state.get("models_error")},
        "ocr": {"tesseract": tesseract_available()},
    }
