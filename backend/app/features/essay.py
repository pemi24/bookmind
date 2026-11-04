"""Essay helper: thesis -> outline with supporting quotes, every quote verified against the book.

Like the quote finder, a quote the model didn't copy exactly from a passage is dropped, and the
book's own text (not the model's copy) is what the reader sees.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, Chapter
from app.features.common import find_verbatim, max_input_chars
from app.ingestion.chunking import page_at
from app.llm import client as llm
from app.llm.prompts import essay as P
from app.retrieval.hybrid import search_book


async def outline(db: AsyncSession, book: Book, thesis: str, max_chapter: int | None, sections: int) -> dict:
    passages = await search_book(db, thesis, book.id, max_chapter=max_chapter,
                                 top_k=max(4, min(16, max_input_chars() // 2200)), user_id=book.user_id)
    if not passages:
        raise llm.LLMError("No passages in the book relate to this thesis. Try rephrasing it.", 422)
    out = await llm.complete_json(P.SYSTEM, P.build_user(book.title, thesis, [p.text for p in passages], sections),
                                  P.EssayOut, max_tokens=12000)

    chapters: dict[int, Chapter] = {}
    dropped = 0
    result_sections = []
    for s in out.sections:
        evidence = []
        for ev in s.evidence:
            if not 1 <= ev.passage <= len(passages):
                dropped += 1
                continue
            p = passages[ev.passage - 1]
            loc = find_verbatim(p.text, ev.quote)
            if loc is None:
                dropped += 1  # not verbatim: never show an invented quote
                continue
            start, end = p.char_start + loc[0], p.char_start + loc[1]
            if p.chapter_id not in chapters:
                chapters[p.chapter_id] = await db.get(Chapter, p.chapter_id)
            ch = chapters[p.chapter_id]
            evidence.append({
                "quote": ch.text[start:end], "explanation": ev.explanation, "chunk_id": p.chunk_id,
                "chapter_id": p.chapter_id, "chapter_position": p.chapter_position, "chapter_title": p.chapter_title,
                "page": page_at(ch.page_map, start), "char_start": start, "char_end": end,
            })
        if s.heading or s.point:
            result_sections.append({"heading": s.heading, "point": s.point, "evidence": evidence})
    return {"title": out.title, "thesis": out.thesis or thesis, "introduction": out.introduction,
            "sections": result_sections, "counterargument": out.counterargument, "conclusion": out.conclusion,
            "dropped_quotes": dropped}


def to_markdown(book: Book, essay: dict) -> str:
    lines = [f"# {essay['title'] or 'Essay outline'}", "", f"*On {book.title}*", "",
             f"**Thesis:** {essay['thesis']}", "", "## Introduction", "", essay["introduction"], ""]
    for i, s in enumerate(essay["sections"], 1):
        lines += [f"## {i}. {s['heading']}", "", s["point"], ""]
        for ev in s["evidence"]:
            where = " · ".join(x for x in [ev["chapter_title"], f"p. {ev['page']}" if ev.get("page") else None] if x)
            lines += [f"> “{ev['quote']}” ({where})", "", f"- {ev['explanation']}", ""]
    lines += ["## Counter-argument", "", essay["counterargument"], "", "## Conclusion", "", essay["conclusion"], ""]
    return "\n".join(lines)
