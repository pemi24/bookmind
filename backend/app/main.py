"""FastAPI application: routers, startup checks, error handling."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from app.auth.deps import current_user
from app.api import account, admin, auth, books, catalog, chat, features, library, notes, stats, study
from app.config import get_settings
from app.db.models import AppMeta, Book
from app.db.session import SessionLocal
from app.features.jobs import fail_interrupted_jobs
from app.ingestion.parsers.pdf import tesseract_available
from app import network
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
for module in (auth, account, admin, books, chat, features, study, notes, catalog, library, stats):
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


@app.get("/api/network", dependencies=[Depends(current_user)])
async def network_info(request: Request):
    """Addresses to open BookMind from a phone or another device on the same Wi-Fi, with QR codes."""
    s = get_settings()
    lan = network.reachable_from_network(s.host)
    built = (_DIST / "index.html").is_file()
    urls = [f"http://{ip}:{s.port}" for ip in network.lan_addresses()]
    # Already opened from another device? Then the address in use is the one to share.
    host = request.url.hostname or ""
    if lan and host and host not in ("localhost", "127.0.0.1", "::1"):
        current = f"http://{host}:{request.url.port or s.port}"
        urls = [current, *[u for u in urls if u != current]]
    return {
        "lan_mode": lan,
        "app_built": built,
        "port": s.port,
        "addresses": [{"url": u, "qr_svg": network.qr_svg(u)} for u in urls[:3]],
    }


# ---------------------------------------------------------------- built web app (phone / LAN mode)
# After `npm run build`, the backend also serves the app itself, so one address works everywhere
# (start.bat lan / ./start.sh --lan). In normal development Vite serves the app instead.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if (_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def web_app(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found."})
        file = (_DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(_DIST):
            # The service worker must always be re-checked, or app updates would never arrive.
            headers = {"Cache-Control": "no-cache"} if file.name in ("sw.js", "manifest.webmanifest") else None
            return FileResponse(file, headers=headers)
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-cache"})
