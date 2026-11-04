"""Chat endpoints: streaming grounded answers (SSE) + persisted conversations."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import scope
from app.auth.deps import CurrentUser, current_user
from app.api.books import get_book_or_404
from app.config import get_settings
from app.db.models import Book, Chapter, Citation, Conversation, Message
from app.db.session import SessionLocal, get_db
from app.features import intent, memory, summaries
from app.llm import client as llm
from app.llm.prompts import chat as chat_prompts
from app.llm.prompts import intent as intent_prompts
from app.llm.prompts import query as query_prompts
from app.retrieval.hybrid import Passage, search_book, search_books

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"], dependencies=[Depends(current_user)])

HISTORY_MESSAGES = 10
# [1], [2, 3], [1-3] — and the "[Passage 1]" / "[source 2]" forms small models tend to write.
_MARKERS = re.compile(r"\[(?:passages?|sources?)?\s*(\d+(?:\s*[,–-]\s*\d+)*)\]", re.IGNORECASE)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    style: str = "default"  # see prompts/chat.py STYLES
    spoiler_chapter: int | None = None  # "I've read up to chapter N" (chapter position)
    persona: str | None = Field(default=None, max_length=200)
    compare_book_ids: list[int] = Field(default_factory=list)  # extra books for compare mode
    resend_from: int | None = None  # id of a user message to replace (with everything after it)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def cited_markers(answer: str, n_passages: int) -> list[int]:
    found: set[int] = set()
    for m in _MARKERS.finditer(answer):
        for part in re.split(r"\s*,\s*", m.group(1)):
            bounds = [int(x) for x in re.split(r"\s*[–-]\s*", part) if x]
            rng = range(bounds[0], bounds[-1] + 1) if len(bounds) == 2 else bounds
            found.update(i for i in rng if 1 <= i <= n_passages)
    return sorted(found)


def source_dict(marker: int, p: Passage) -> dict:
    return {
        "marker": marker, "chunk_id": p.chunk_id, "book_id": p.book_id, "book_title": p.book_title,
        "chapter_id": p.chapter_id, "chapter_position": p.chapter_position, "chapter_title": p.chapter_title,
        "page_start": p.page_start, "page_end": p.page_end, "char_start": p.char_start, "char_end": p.char_end,
        "score": round(p.score, 4), "text": p.text,
    }


async def _history(db: AsyncSession, conversation_id: int) -> list[dict]:
    rows = (await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc()).limit(HISTORY_MESSAGES)
    )).scalars().all()
    # Local models have small context windows: keep fewer, shorter turns.
    keep, cap = (6, 1500) if llm.provider().local else (HISTORY_MESSAGES, 20_000)
    msgs = [{"role": m.role, "content": m.content[:cap]} for m in reversed(rows)][-keep:]
    # Keep strict user/assistant alternation (a failed answer leaves a lone user turn).
    clean: list[dict] = []
    for m in msgs:
        if clean and clean[-1]["role"] == m["role"]:
            clean[-1] = m
        else:
            clean.append(m)
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    if clean and clean[-1]["role"] == "user":
        clean.pop()
    return clean


def _rewrite_mode() -> str:
    mode = get_settings().query_rewrite
    if mode == "auto":
        return "heuristic" if llm.provider().local else "llm"
    return mode


async def _rewrite_query(history: list[dict], question: str) -> str:
    """Make follow-ups ("what did he do next?") searchable on their own."""
    if not history:
        return question
    mode = _rewrite_mode()
    if mode == "off":
        return question
    if mode == "heuristic":
        # No extra model call (slow on CPU): search with the previous question as context.
        prev = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        return f"{prev[:300]} {question}".strip()
    try:
        q = await llm.complete_text(
            query_prompts.SYSTEM,
            query_prompts.build_user([(m["role"], m["content"]) for m in history], question),
            model=llm.provider().fast_model, effort="low", max_tokens=300,
        )
        return q.strip().strip('"')[:500] or question
    except llm.LLMError as e:
        log.warning("Query rewrite failed, using raw question: %s", e.message)
        return question


async def _overview(db: AsyncSession, book: Book, max_chapter: int | None) -> tuple[str, bool]:
    """Book memory: each chapter's summary (within the spoiler limit) and a saved whole-book summary, if any.
    Also says whether any chapter summary exists yet (books whose memory isn't built only list chapter titles)."""
    chapters = await memory.chapter_memories(db, book.id, max_chapter)
    summary = None
    for length in ("short", "medium", "detailed"):
        if hit := await summaries.cached(db, book.id, None, length, max_chapter):
            summary = hit.content
            break
    # Small local models have little context to spare.
    text = chat_prompts.build_overview(book.title, book.author, chapters, summary,
                                       max_chars=1500 if llm.provider().local else 14000)
    return text, bool(summary) or any(m for _, m in chapters)


async def _search_again(book_id: int, book_title: str, question: str, max_chapter: int | None,
                        seen: list[Passage], *, user_id: int) -> list[Passage]:
    """Passages found with alternative queries, new ones first; [] if nothing new turned up."""
    try:
        out = await llm.complete_json(query_prompts.EXPAND_SYSTEM, query_prompts.build_expand(question, book_title),
                                      query_prompts.ExpandOut, model=llm.provider().fast_model, max_tokens=400)
    except llm.LLMError as e:
        log.warning("Second search skipped: %s", e.message)
        return []
    queries = [q.strip() for q in out.queries if isinstance(q, str) and q.strip()][:3]
    known = {p.chunk_id for p in seen}
    found: dict[int, Passage] = {}
    async with SessionLocal() as sdb:
        for q in queries:
            for p in await search_book(sdb, q, book_id, max_chapter=max_chapter, top_k=6, user_id=user_id):
                if p.chunk_id not in known:
                    found.setdefault(p.chunk_id, p)
    if not found:
        return []
    k = llm.provider().default_top_k
    new = sorted(found.values(), key=lambda p: p.score, reverse=True)[: max(k // 2, 3)]
    return (new + seen)[:k]


async def check_daily_messages(db: AsyncSession, user) -> None:
    limit = get_settings().daily_message_limit
    if not limit:
        return
    since = datetime.now(timezone.utc) - timedelta(days=1)
    sent = await db.scalar(
        select(func.count()).select_from(Message).join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == user.id, Message.role == "user", Message.created_at >= since))
    if sent >= limit:
        raise HTTPException(429, f"You've reached today's limit of {limit} messages (DAILY_MESSAGE_LIMIT). "
                                 "It frees up gradually over the next 24 hours.")


@router.post("/books/{book_id}/chat")
async def chat(user: CurrentUser, book_id: int, req: ChatRequest, db: AsyncSession = Depends(get_db)):
    book = await get_book_or_404(db, book_id, user)
    if book.status != "ready":
        raise HTTPException(409, "This book is still being indexed. Try again when it's ready.")
    await check_daily_messages(db, user)
    if not llm.llm_configured():
        raise HTTPException(503, llm.not_configured_message())
    if req.style not in chat_prompts.STYLES:
        raise HTTPException(400, f"Unknown style. Options: {', '.join(chat_prompts.STYLES)}")

    compare_ids = [b for b in dict.fromkeys(req.compare_book_ids) if b != book_id]
    for bid in compare_ids:
        other = await get_book_or_404(db, bid, user)
        if other.status != "ready":
            raise HTTPException(409, f"'{other.title}' is not indexed yet.")

    spoiler = None
    if req.spoiler_chapter is not None:
        title = await db.scalar(select(Chapter.title).where(
            Chapter.book_id == book_id, Chapter.position == req.spoiler_chapter))
        if title is None:
            raise HTTPException(400, "Spoiler guard chapter does not exist in this book.")
        spoiler = (req.spoiler_chapter, title)

    if req.conversation_id:
        conv = await scope.conversation(db, req.conversation_id, user)
        if conv.book_id != book_id:
            raise HTTPException(404, "Conversation not found.")
    else:
        mode = "compare" if compare_ids else ("persona" if req.persona else "chat")
        conv = Conversation(user_id=user.id, book_id=book_id, book_ids=[book_id, *compare_ids], mode=mode,
                            persona=req.persona, title=req.message.strip()[:120])
        db.add(conv)
        await db.flush()

    if req.resend_from is not None:
        # Resend / edit: drop that question and everything after it, so the old turn
        # doesn't linger in the history used for follow-ups.
        first = await db.get(Message, req.resend_from)
        if first is None or first.conversation_id != conv.id or first.role != "user":
            raise HTTPException(404, "Message to resend not found in this conversation.")
        await db.execute(delete(Message).where(Message.conversation_id == conv.id, Message.id >= first.id))
        await db.flush()

    history = await _history(db, conv.id)
    book_title, book_author = book.title, book.author
    starters = intent_prompts.starter_questions(book.suggested_questions or [])
    compare_titles = [(await get_book_or_404(db, b, user)).title for b in compare_ids]
    uid = user.id
    overview, has_memory = (None, False) if compare_ids else await _overview(db, book, req.spoiler_chapter)
    meta = {"style": req.style, "spoiler_chapter": req.spoiler_chapter, "persona": req.persona,
            "compare_book_ids": compare_ids}
    user_msg = Message(conversation_id=conv.id, role="user", content=req.message, meta=meta)
    db.add(user_msg)
    await db.commit()
    conv_id, user_msg_id = conv.id, user_msg.id

    async def reply_without_book(text: str, kind: str):
        """Small talk, questions about the app, off-topic or nothing found: a direct reply, no model answer."""
        yield sse("intent", {"intent": kind})
        yield sse("delta", {"text": text})
        async with SessionLocal() as wdb:
            msg = Message(conversation_id=conv_id, role="assistant", content=text, meta={**meta, "intent": kind})
            wdb.add(msg)
            await wdb.flush()
            conv_row = await wdb.get(Conversation, conv_id)
            conv_row.updated_at = func.now()
            await wdb.commit()
            yield sse("done", {"message_id": msg.id, "cited": [], "intent": kind})

    async def stream():
        yield sse("conversation", {"id": conv_id, "user_message_id": user_msg_id})
        answer = ""
        try:
            yield sse("status", {"stage": "searching"})
            # 1. What kind of message is this? (Talking to a character: everything goes to the character.)
            route = intent.Route("book_question", by="persona") if req.persona else                 await intent.route(req.message, history, book_title)
            checked: list[Passage] | None = None
            if route.intent == "off_topic":
                # Double-check against the book before refusing: a strong match means it's about the book.
                async with SessionLocal() as sdb:
                    checked = await search_book(sdb, req.message, book_id, max_chapter=req.spoiler_chapter,
                                                user_id=uid)
                if checked and checked[0].score >= intent.OFF_TOPIC_MAX_RELEVANCE:
                    route = intent.Route("book_question", by="checked")
            if route.intent == "smalltalk":
                async for ev in reply_without_book(intent_prompts.smalltalk_reply(route.kind, book_title, book_author),
                                                   "smalltalk"):
                    yield ev
                return
            if route.intent == "meta":
                async for ev in reply_without_book(intent_prompts.meta_reply(book_title, book_author, compare_titles),
                                                   "meta"):
                    yield ev
                return
            if route.intent == "off_topic":
                async for ev in reply_without_book(intent_prompts.off_topic_reply(book_title, starters, book_author),
                                                   "off_topic"):
                    yield ev
                return

            # 2. A book question: standalone search query, then retrieval.
            query = await _rewrite_query(history, req.message)
            if checked is not None and query == req.message and not compare_ids:
                passages = checked
            else:
                async with SessionLocal() as sdb:
                    if compare_ids:
                        passages = await search_books(sdb, query, [book_id, *compare_ids],
                                                      {book_id: req.spoiler_chapter}, per_book_k=5, user_id=uid)
                    else:
                        passages = await search_book(sdb, query, book_id, max_chapter=req.spoiler_chapter,
                                                     user_id=uid)
            sources = [source_dict(i, p) for i, p in enumerate(passages, start=1)]
            yield sse("sources", {"query": query, "sources": sources})
            if not passages:
                # Grounding: with nothing retrieved, the model is never asked to answer from what it knows.
                async for ev in reply_without_book(intent_prompts.not_found_reply(book_title, starters), "not_found"):
                    yield ev
                return

            yield sse("status", {"stage": "answering"})
            system = chat_prompts.build_system(req.style, spoiler, bool(compare_ids), req.persona, overview,
                                               book_title=book_title, author=book_author)
            messages = [*history, {"role": "user", "content": chat_prompts.build_user_turn(req.message, passages, memory=has_memory)}]
            async for delta in llm.stream_text(system, messages):
                answer += delta
                yield sse("delta", {"text": delta})

            # Second chance before "the book doesn't say": search again with other wordings
            # (other names, the book's own vocabulary) and answer from what that finds.
            if chat_prompts.admits_gap(answer) and not compare_ids:
                yield sse("status", {"stage": "searching_more"})
                more = await _search_again(book_id, book_title, req.message, req.spoiler_chapter, passages,
                                           user_id=uid)
                if more:
                    passages = more
                    sources = [source_dict(i, p) for i, p in enumerate(passages, start=1)]
                    yield sse("reset", {})
                    yield sse("sources", {"query": query, "sources": sources})
                    yield sse("status", {"stage": "answering"})
                    messages[-1] = {"role": "user", "content": chat_prompts.build_user_turn(req.message, passages, memory=has_memory)}
                    answer = ""
                    async for delta in llm.stream_text(system, messages):
                        answer += delta
                        yield sse("delta", {"text": delta})

            # A short "the book doesn't say" answer cites nothing, even if the model tacked on a [n].
            used = [] if chat_prompts.is_not_found(answer) else cited_markers(answer, len(passages))
            async with SessionLocal() as wdb:
                msg = Message(conversation_id=conv_id, role="assistant", content=answer,
                              meta={**meta, "query": query, "sources": sources, "intent": "book_question"})
                wdb.add(msg)
                await wdb.flush()
                for mk in used:
                    p = passages[mk - 1]
                    wdb.add(Citation(message_id=msg.id, chunk_id=p.chunk_id, marker=mk, score=p.score))
                conv_row = await wdb.get(Conversation, conv_id)
                conv_row.updated_at = func.now()
                await wdb.commit()
                yield sse("done", {"message_id": msg.id, "cited": used, "intent": "book_question"})
        except llm.LLMError as e:
            yield sse("error", {"message": e.message, "partial": answer})
        except Exception as e:  # noqa: BLE001
            log.exception("Chat failed")
            yield sse("error", {"message": f"Something went wrong while answering: {e}", "partial": answer})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/books/{book_id}/conversations")
async def list_conversations(user: CurrentUser, book_id: int, db: AsyncSession = Depends(get_db)):
    await get_book_or_404(db, book_id, user)
    rows = (await db.execute(
        select(Conversation).where(Conversation.book_id == book_id, Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )).scalars().all()
    return [{"id": c.id, "title": c.title, "mode": c.mode, "persona": c.persona, "book_ids": c.book_ids,
             "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/conversations/{conversation_id}")
async def get_conversation(user: CurrentUser, conversation_id: int, db: AsyncSession = Depends(get_db)):
    conv = await scope.conversation(db, conversation_id, user)
    msgs = (await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )).scalars().all()
    return {
        "id": conv.id, "book_id": conv.book_id, "book_ids": conv.book_ids, "title": conv.title,
        "mode": conv.mode, "persona": conv.persona,
        "messages": [{
            "id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat(),
            "sources": (m.meta or {}).get("sources", []), "cited": [c.marker for c in m.citations],
            "meta": {k: v for k, v in (m.meta or {}).items() if k != "sources"},
        } for m in msgs],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(user: CurrentUser, conversation_id: int, db: AsyncSession = Depends(get_db)):
    conv = await scope.conversation(db, conversation_id, user)
    await db.delete(conv)
    await db.commit()


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(user: CurrentUser, conversation_id: int, req: RenameRequest,
                              db: AsyncSession = Depends(get_db)):
    conv = await scope.conversation(db, conversation_id, user)
    title = " ".join(req.title.split())[:120]
    if not title:
        raise HTTPException(422, "A chat name can't be empty.")
    conv.title = title
    await db.commit()
    return {"id": conv.id, "title": conv.title}
