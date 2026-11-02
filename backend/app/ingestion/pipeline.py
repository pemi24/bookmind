"""Ingestion pipeline: parse -> clean -> chapters -> chunk -> embed -> store.

Runs as an asyncio background task. CPU-heavy steps run in worker threads so the API
stays responsive; progress is written to `books.progress/status_message`, which the
SSE endpoint streams to the browser. Only one book indexes at a time (laptop-friendly);
others wait in a queue.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, update

from app.config import get_settings
from app.db.models import Book, Chapter, Chunk
from app.db.session import SessionLocal
from app.ingestion.chapters import ChapterData, detect_chapters
from app.ingestion.chunking import chunk_text, page_at
from app.ingestion.cleaning import clean_document
from app.ingestion.parsers import ParseError, parse_file
from app.llm import client as llm
from app.llm.prompts import book as book_prompts
from app.retrieval.embeddings import get_embedder

log = logging.getLogger(__name__)

_queue_lock = asyncio.Lock()
_tasks: set[asyncio.Task] = set()

# Progress budget for each stage (fractions of the bar).
_PARSE = (0.02, 0.30)
_STRUCTURE = 0.35
_EMBED = (0.38, 0.97)
EMBED_BATCH = 64


class _Progress:
    """Thread-safe progress holder flushed to the DB by an async loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.value, self.message, self._dirty = 0.0, "Queued", True

    def set(self, value: float, message: str) -> None:
        with self._lock:
            self.value, self.message, self._dirty = value, message, True

    def take(self) -> tuple[float, str] | None:
        with self._lock:
            if not self._dirty:
                return None
            self._dirty = False
            return self.value, self.message


async def _flusher(book_id: int, prog: _Progress, stop: asyncio.Event) -> None:
    while True:
        item = prog.take()
        if item:
            async with SessionLocal() as db:
                await db.execute(
                    update(Book).where(Book.id == book_id).values(progress=item[0], status_message=item[1])
                )
                await db.commit()
        if stop.is_set():
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.4)
        except TimeoutError:
            pass


def title_from_filename(filename: str) -> str:
    """Provisional title until the file's own metadata is read ("my_book-v2.pdf" -> "my book v2")."""
    stem = Path(filename).stem
    return re.sub(r"[_\-]+", " ", stem).strip() or stem


def schedule_ingestion(book_id: int) -> None:
    task = asyncio.create_task(ingest_book(book_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _parse_and_structure(path: Path, prog: _Progress):
    def on_parse(f: float, msg: str) -> None:
        prog.set(_PARSE[0] + (_PARSE[1] - _PARSE[0]) * f, msg)

    doc = parse_file(path, on_parse)
    prog.set(_PARSE[1], "Cleaning text")
    clean_document(doc)
    prog.set(_STRUCTURE, "Detecting chapters")
    chapters = detect_chapters(doc)
    if not chapters or not any(ch.text.strip() for ch in chapters):
        raise ParseError("No readable text was found in this file.")
    return doc, chapters


async def ingest_book(book_id: int) -> None:
    prog = _Progress()
    stop = asyncio.Event()
    async with SessionLocal() as db:
        await db.execute(
            update(Book).where(Book.id == book_id)
            .values(status="pending", progress=0, status_message="Queued", error=None)
        )
        await db.commit()

    async with _queue_lock:
        flusher = asyncio.create_task(_flusher(book_id, prog, stop))
        started = time.monotonic()
        try:
            result = await _run(book_id, prog)
            stop.set()
            await flusher
            if result is None:
                return
            await _finalize(book_id, *result)
            log.info("Indexed book %s in %.1fs", book_id, time.monotonic() - started)
        except Exception as e:  # noqa: BLE001
            stop.set()
            await flusher
            if isinstance(e, ParseError):
                msg = str(e)
            else:
                log.exception("Indexing failed for book %s", book_id)
                msg = f"Indexing failed: {e}"
            async with SessionLocal() as db:
                await db.execute(
                    update(Book).where(Book.id == book_id)
                    .values(status="failed", error=msg, status_message="Failed")
                )
                await db.commit()
            return

    # Non-critical enrichment (needs the LLM); failures only add a warning.
    await _profile_book(book_id)


async def _run(book_id: int, prog: _Progress):
    s = get_settings()
    async with SessionLocal() as db:
        book = await db.get(Book, book_id)
        if book is None:
            return
        book.status, book.error = "processing", None
        await db.commit()
        path = Path(book.file_path)
        if not path.exists():
            raise ParseError("The uploaded file is missing from disk. Delete this book and upload it again.")

    prog.set(_PARSE[0], "Extracting text")
    doc, chapters = await asyncio.to_thread(_parse_and_structure, path, prog)

    # Chunk every chapter (cheap) so we know the total for the progress bar.
    planned: list[tuple[ChapterData, list]] = [
        (ch, chunk_text(ch.text, s.chunk_target_tokens, s.chunk_max_tokens, s.chunk_overlap_tokens))
        for ch in chapters
    ]
    total = sum(len(spans) for _, spans in planned)
    if total == 0:
        raise ParseError("No readable text was found in this file.")

    # One transaction: a re-index replaces old data atomically. The books row itself is only
    # touched at the end, so the progress flusher (separate session) is never blocked by a row lock.
    async with SessionLocal() as db:
        await db.execute(delete(Chapter).where(Chapter.book_id == book_id))  # chunks cascade

        chapter_rows: list[Chapter] = []
        for ch in chapters:
            row = Chapter(
                book_id=book_id, position=ch.position, title=ch.title, text=ch.text,
                page_map=ch.page_map, start_page=ch.start_page, end_page=ch.end_page,
            )
            db.add(row)
            chapter_rows.append(row)
        await db.flush()

        # Embed + insert in batches.
        embedder = get_embedder()
        prog.set(_EMBED[0], f"Loading embedding model, then embedding {total} passages")
        pending: list[tuple[Chapter, ChapterData, object]] = [
            (row, ch, span) for row, (ch, spans) in zip(chapter_rows, planned) for span in spans
        ]
        done = 0
        global_pos = 0
        for i in range(0, len(pending), EMBED_BATCH):
            batch = pending[i : i + EMBED_BATCH]
            # Prefix chapter title so short passages carry context into the vector.
            inputs = [f"{row.title}\n{span.text}" for row, _, span in batch]
            vectors = await asyncio.to_thread(embedder.embed_documents, inputs)
            for (row, ch, span), vec in zip(batch, vectors):
                db.add(Chunk(
                    book_id=book_id, chapter_id=row.id, chapter_position=row.position,
                    position=global_pos, text=span.text,
                    char_start=span.char_start, char_end=span.char_end,
                    page_start=page_at(ch.page_map, span.char_start),
                    page_end=page_at(ch.page_map, max(span.char_end - 1, span.char_start)),
                    token_count=span.token_count, embedding=vec,
                ))
                global_pos += 1
            await db.flush()
            done += len(batch)
            frac = _EMBED[0] + (_EMBED[1] - _EMBED[0]) * done / total
            prog.set(frac, f"Embedding passages {done} / {total}")

        await db.commit()
    return doc, len(chapters), total


async def _finalize(book_id: int, doc, n_chapters: int, total: int) -> None:
    """Runs after the progress flusher has stopped, so nothing overwrites the final state."""
    async with SessionLocal() as db:
        book = await db.get(Book, book_id)
        if doc.title and (book.title == title_from_filename(book.filename) or not book.title):
            book.title = doc.title[:500]
        if doc.author and not book.author:
            book.author = doc.author[:500]
        book.page_count = len(doc.pages)
        book.pages_estimated = doc.pages_estimated
        book.warnings = list(doc.warnings)
        book.embedding_model = get_embedder().name
        book.status = "ready"
        book.progress = 1.0
        book.status_message = f"Indexed {n_chapters} chapters, {total} passages"
        book.indexed_at = datetime.now(timezone.utc)
        await db.commit()


async def _profile_book(book_id: int) -> None:
    """Fiction/non-fiction + suggested questions. Best effort."""
    if not llm.llm_configured():
        return
    async with SessionLocal() as db:
        book = await db.get(Book, book_id)
        chapters = (await db.execute(
            select(Chapter.title).where(Chapter.book_id == book_id).order_by(Chapter.position)
        )).scalars().all()
        n = (await db.execute(select(Chunk.id).where(Chunk.book_id == book_id))).scalars().all()
        picks = [n[int(len(n) * f)] for f in (0.05, 0.25, 0.5, 0.75)] if n else []
        samples = (await db.execute(select(Chunk.text).where(Chunk.id.in_(picks)))).scalars().all()
        title, author = book.title, book.author
    try:
        profile = await llm.complete_json(
            book_prompts.SYSTEM,
            book_prompts.build_user(title, author, list(chapters), list(samples)),
            book_prompts.BookProfile,
            max_tokens=4000,
        )
        values = {"is_fiction": profile.is_fiction, "suggested_questions": profile.questions[:8]}
    except llm.LLMError as e:
        log.warning("Book profiling failed: %s", e.message)
        async with SessionLocal() as db:
            book = await db.get(Book, book_id)
            book.warnings = [*(book.warnings or []), f"Suggested questions unavailable: {e.message}"]
            await db.commit()
        return
    async with SessionLocal() as db:
        await db.execute(update(Book).where(Book.id == book_id).values(**values))
        await db.commit()
