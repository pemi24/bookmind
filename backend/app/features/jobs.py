"""Background jobs for long, per-book LLM work (book analysis, whole-book summaries).

Each job has a row in `feature_jobs` (status/progress/error) that the UI polls.
Only one job per (book, kind) runs at a time; starting it again returns the running one.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select, update

from app.db.models import FeatureJob
from app.db.session import SessionLocal
from app.llm.client import LLMError

log = logging.getLogger(__name__)
_running: dict[tuple[int, str], asyncio.Task] = {}


class JobContext:
    def __init__(self, job_id: int, book_id: int) -> None:
        self.job_id = job_id
        self.book_id = book_id

    async def progress(self, fraction: float) -> None:
        async with SessionLocal() as db:
            await db.execute(update(FeatureJob).where(FeatureJob.id == self.job_id)
                             .values(progress=round(min(max(fraction, 0.0), 1.0), 4)))
            await db.commit()


def job_dict(job: FeatureJob | None) -> dict | None:
    if job is None:
        return None
    return {"id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress, "error": job.error,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None}


async def latest_job(db, book_id: int, kind: str) -> FeatureJob | None:
    return (await db.execute(
        select(FeatureJob).where(FeatureJob.book_id == book_id, FeatureJob.kind == kind)
        .order_by(FeatureJob.id.desc()).limit(1)
    )).scalars().first()


def is_running(book_id: int, kind: str) -> bool:
    t = _running.get((book_id, kind))
    return t is not None and not t.done()


async def start_job(book_id: int, kind: str, work: Callable[[JobContext], Awaitable[None]]) -> dict:
    async with SessionLocal() as db:
        if is_running(book_id, kind):
            return job_dict(await latest_job(db, book_id, kind))
        job = FeatureJob(book_id=book_id, kind=kind, status="running", progress=0.0)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id, out = job.id, job_dict(job)

    async def run() -> None:
        ctx = JobContext(job_id, book_id)
        status, error = "done", None
        try:
            await work(ctx)
        except LLMError as e:
            status, error = "failed", e.message
        except asyncio.CancelledError:
            status, error = "failed", "Cancelled (server stopped)."
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("Job %s/%s failed", book_id, kind)
            status, error = "failed", f"{type(e).__name__}: {e}"
        finally:
            async with SessionLocal() as db:
                values = {"status": status, "error": error}
                if status == "done":
                    values["progress"] = 1.0
                await db.execute(update(FeatureJob).where(FeatureJob.id == job_id).values(**values))
                await db.commit()

    _running[(book_id, kind)] = asyncio.create_task(run())
    return out


async def fail_interrupted_jobs() -> None:
    """Called at startup: jobs don't survive a restart."""
    async with SessionLocal() as db:
        await db.execute(update(FeatureJob).where(FeatureJob.status == "running")
                         .values(status="failed", error="Interrupted (server restarted). Start it again."))
        await db.commit()
