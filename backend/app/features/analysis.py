"""Book analysis job: per-chapter extraction of entities, relations and key events.

One LLM call per chapter (or chapter part) returns all three, which powers the
Explorer (glossary + relationship graph / concept map) and the Timeline. Everything is
stored with the chapter where it first appears, so the spoiler guard can filter it.

Chapters are processed in small concurrent batches; names already found are passed to
later chapters so the model reuses canonical spellings, and results are merged by
normalized name / alias.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models import Book, Chapter, Chunk, Entity, EntityRelation, TimelineEvent
from app.db.session import SessionLocal
from app.features.common import chunk_for_offset, find_verbatim, normalize_name, parallel_requests, split_text
from app.features.jobs import JobContext
from app.llm import client as llm
from app.llm.prompts import analysis as P

JOB_KIND = "analysis"


@dataclass
class _Ent:
    name: str
    kind: str
    aliases: set[str] = field(default_factory=set)
    details: list[dict] = field(default_factory=list)  # [{"chapter": n, "text": ...}]
    first_chapter: int = 0
    importance: int = 1


class EntityMerger:
    """Merges per-chapter entity mentions into one record per real entity."""

    def __init__(self) -> None:
        self.entities: list[_Ent] = []
        self._index: dict[str, _Ent] = {}

    def find(self, name: str) -> _Ent | None:
        return self._index.get(normalize_name(name))

    def add(self, e: P.EntityOut, chapter: int) -> _Ent:
        hit = self.find(e.name) or next((self.find(a) for a in e.aliases if self.find(a)), None)
        if hit is None:
            hit = _Ent(name=e.name.strip(), kind=e.kind, first_chapter=chapter)
            self.entities.append(hit)
        hit.importance = max(hit.importance, min(max(int(e.importance), 1), 5))
        hit.first_chapter = min(hit.first_chapter, chapter)
        text = e.description.strip()
        if text and not any(d["chapter"] == chapter for d in hit.details):
            hit.details.append({"chapter": chapter, "text": text})
        for alias in [e.name, *e.aliases]:
            alias = alias.strip()
            if alias and normalize_name(alias) != normalize_name(hit.name):
                hit.aliases.add(alias)
            if alias:
                self._index.setdefault(normalize_name(alias), hit)
        return hit

    def known_names(self) -> list[str]:
        return [e.name for e in sorted(self.entities, key=lambda x: -x.importance)]


async def _analyze_chapter(book_title: str, is_fiction: bool | None, known: list[str],
                           title: str, text: str) -> list[P.ChapterAnalysis]:
    s = get_settings()
    parts = split_text(text)
    out = []
    for i, part in enumerate(parts, 1):
        label = title if len(parts) == 1 else f"{title} (part {i} of {len(parts)})"
        out.append(await llm.complete_json(
            P.SYSTEM, P.build_user(book_title, is_fiction, known, label, part), P.ChapterAnalysis,
            model=s.llm_fast_model, effort=s.llm_task_effort, max_tokens=16000,
        ))
    return out


def analysis_job(book_id: int):
    async def work(ctx: JobContext) -> None:
        async with SessionLocal() as db:
            book = await db.get(Book, book_id)
            chapters = list((await db.execute(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position)
            )).scalars())
            chunks = list((await db.execute(
                select(Chunk.id, Chunk.chapter_id, Chunk.char_start, Chunk.char_end)
                .where(Chunk.book_id == book_id).order_by(Chunk.position)
            )).all())
            title, is_fiction = book.title, book.is_fiction
            ch_data = [(c.id, c.position, c.title, c.text) for c in chapters]

        merger = EntityMerger()
        relations: dict[tuple[str, str, str], dict] = {}
        events: list[dict] = []

        # Chapters per concurrent batch (1 for local models); names found so far are passed on.
        size = parallel_requests()
        for b in range(0, len(ch_data), size):
            batch = ch_data[b:b + size]
            known = merger.known_names()
            results = await asyncio.gather(*(
                _analyze_chapter(title, is_fiction, known, t, txt) for _, _, t, txt in batch
            ))
            for (cid, pos, _, text), analyses in zip(batch, results):
                for a in analyses:
                    names = {normalize_name(e.name): merger.add(e, pos) for e in a.entities}
                    for r in a.relations:
                        src = merger.find(r.source) or names.get(normalize_name(r.source))
                        tgt = merger.find(r.target) or names.get(normalize_name(r.target))
                        if not src or not tgt or src is tgt:
                            continue
                        key = (src.name, tgt.name, r.relation.strip().lower())
                        relations.setdefault(key, {"source": src, "target": tgt, "relation": r.relation.strip(),
                                                   "description": r.description.strip(), "first_chapter": pos})
                    for ev in a.events:
                        loc = find_verbatim(text, ev.evidence)
                        chunk = chunk_for_offset(chunks, cid, loc[0]) if loc else None
                        if chunk is None:  # fall back to the chapter's first passage
                            chunk = next((c for c in chunks if c.chapter_id == cid), None)
                        events.append({"title": ev.title.strip(), "description": ev.description.strip(),
                                       "when": (ev.when or "").strip() or None,
                                       "importance": min(max(int(ev.importance), 1), 5),
                                       "chapter": pos, "offset": loc[0] if loc else 10**9,
                                       "chunk_id": chunk.id if chunk else None})
            await ctx.progress(0.95 * min(b + size, len(ch_data)) / len(ch_data))

        # Replace any previous analysis atomically.
        async with SessionLocal() as db:
            await db.execute(delete(EntityRelation).where(EntityRelation.book_id == book_id))
            await db.execute(delete(Entity).where(Entity.book_id == book_id))
            await db.execute(delete(TimelineEvent).where(TimelineEvent.book_id == book_id))
            rows: dict[int, Entity] = {}
            for e in merger.entities:
                e.details.sort(key=lambda d: d["chapter"])
                row = Entity(book_id=book_id, kind=e.kind, name=e.name[:300], aliases=sorted(a[:300] for a in e.aliases),
                             description=e.details[0]["text"] if e.details else "", details=e.details,
                             first_chapter=e.first_chapter, importance=e.importance, chunk_ids=[])
                db.add(row)
                rows[id(e)] = row
            await db.flush()
            for r in relations.values():
                db.add(EntityRelation(book_id=book_id, source_id=rows[id(r["source"])].id,
                                      target_id=rows[id(r["target"])].id, relation=r["relation"][:200],
                                      description=r["description"], first_chapter=r["first_chapter"]))
            events.sort(key=lambda e: (e["chapter"], e["offset"]))
            for i, e in enumerate(events):
                db.add(TimelineEvent(book_id=book_id, position=i, title=e["title"][:300], description=e["description"],
                                     when_label=(e["when"] or None) and e["when"][:200],
                                     chapter_position=e["chapter"], chunk_id=e["chunk_id"], importance=e["importance"]))
            await db.commit()

    return work
