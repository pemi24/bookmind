"""Intent routing (small talk / meta / book question / off-topic) and the chat flow around it."""
from __future__ import annotations

import json

import httpx

from tests.conftest import signed_in
import pytest

from app.llm.prompts import intent as P
from tests.test_features_api import fake_llm  # noqa: F401  (fixture)
from tests.test_retrieval_api import BOOK, C1, C2, C3, _wait_ready

ASYNC = pytest.mark.asyncio(loop_scope="session")

NOT_FOUND_WORDS = ("doesn't say", "does not say", "not in the book", "couldn't find", "not found")


# ---------------------------------------------------------------- rules and replies (no model)

@pytest.mark.parametrize("message,intent,kind", [
    ("hello", "smalltalk", "greeting"), ("Hello!", "smalltalk", "greeting"), ("hi there", "smalltalk", "greeting"),
    ("hey 👋", "smalltalk", "greeting"), ("good morning", "smalltalk", "greeting"),
    ("how are you?", "smalltalk", "how_are_you"), ("thanks!", "smalltalk", "thanks"),
    ("thank you so much", "smalltalk", "thanks"), ("ok thanks", "smalltalk", "thanks"), ("bye", "smalltalk", "goodbye"),
    ("ok", "smalltalk", "ack"), ("you're awesome", "smalltalk", "compliment"),
    ("what can you do?", "meta", "features"), ("how do I use this?", "meta", "features"), ("help", "meta", "features"),
])
def test_rules_recognise_obvious_messages(message, intent, kind):
    assert P.rule_intent(message) == (intent, kind)


@pytest.mark.parametrize("message", [
    "What is this book about?", "hello, who is Mara?", "who won the 2018 World Cup?", "yes", "tell me more",
    "Why did the keeper climb the stairs?",
])
def test_rules_leave_everything_else_to_the_router(message):
    assert P.rule_intent(message) is None  # book questions are never caught as small talk


def test_follow_ups_and_parsing():
    assert P.is_follow_up("tell me more") and P.is_follow_up("Why did he do that?") and P.is_follow_up("what happened next")
    assert not P.is_follow_up("who won the 2018 World Cup?")
    assert P.mentions_book("What happens in chapter 2?", "Anything") and P.mentions_book("Who is the keeper?", "The Lighthouse Keeper")
    assert [P.parse_intent(x) for x in ("smalltalk", "Meta.", "offtopic", "book", "", "I think it is about the book")] == [
        "smalltalk", "meta", "off_topic", "book_question", "book_question", "book_question"]


def test_replies_are_friendly_mention_the_book_and_never_say_not_found():
    title = "The Lighthouse Keeper"
    for kind in ("greeting", "how_are_you", "thanks", "goodbye", "compliment", "ack"):
        r = P.smalltalk_reply(kind, title)
        assert f"*{title}*" in r and not any(w in r.lower() for w in NOT_FOUND_WORDS)
    assert P.smalltalk_reply("greeting", title).startswith("Hello! How may I assist you with")
    meta = P.meta_reply(title, "Test Author")
    assert "by Test Author" in meta and "Summarize" in meta and "Quiz" in meta
    off = P.off_topic_reply(title, ["Who is Mara?", "What is in the cellar?", "Why the storm?", "Fourth?"])
    assert "only answer from the book" in off and off.count("\n- ") == 3
    assert P.starter_questions([]) == list(P.DEFAULT_STARTERS) and len(P.starter_questions(["a", "b", "c"])) == 5


@ASYNC
async def test_router_uses_the_model_only_when_needed(monkeypatch):
    from app.features import intent
    from app.llm import client

    calls = []

    async def classify(system, user, **kw):
        calls.append(user)
        return replies.pop(0)

    monkeypatch.setattr(client, "complete_text", classify)
    replies = ["offtopic", "meta", "smalltalk", "banana"]
    assert (await intent.route("hello", [], "Book")).intent == "smalltalk" and calls == []  # rule, no model call
    assert (await intent.route("tell me more", [{"role": "assistant", "content": "Mara keeps it [1]."}], "Book")).intent == "book_question"
    assert (await intent.route("What happens in chapter 2?", [], "Book")).intent == "book_question" and calls == []
    assert (await intent.route("who won the 2018 World Cup?", [], "Book")).intent == "off_topic"
    assert (await intent.route("are you a robot or a person", [], "Book")).intent == "meta"
    # A short reply to the assistant's own question continues the book conversation.
    asked = [{"role": "assistant", "content": "Would you like to know about the cellar?"}]
    assert (await intent.route("yes please", asked, "Book")).intent == "book_question"
    assert (await intent.route("hmm whatever", [], "Book")).intent == "book_question"  # unclear answer -> book
    assert len(calls) == 4

    async def broken(system, user, **kw):
        raise client.LLMError("down", 503)

    monkeypatch.setattr(client, "complete_text", broken)
    assert (await intent.route("something odd", [], "Book")) == intent.Route("book_question", by="default")


# ---------------------------------------------------------------- the chat flow end to end

def _events(text: str) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in text.splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            out.append((ev, json.loads(line[6:])))
    return out


def _answer(events) -> str:
    text = ""
    for ev, d in events:
        if ev == "reset":
            text = ""
        elif ev == "delta":
            text += d["text"]
    return text


@ASYNC
async def test_chat_flow_routes_messages(test_db, fake_llm, monkeypatch):  # noqa: F811
    from app.api import chat as chat_api
    from app.llm import client
    from app.llm.prompts import intent as ip
    from app.main import app

    answered = []  # passages each model answer was given

    async def stream_text(system, messages, **kw):
        user = messages[-1]["content"]
        answered.append(user.count("] ("))
        if "colour" in user:
            yield "The book doesn't say. You could ask what Mara found in the sand."
        else:
            yield "Mara keeps the lighthouse on the northern cliff [1]."

    real_text = client.complete_text

    async def complete_text(system, user, **kw):
        if system == ip.CLASSIFY_SYSTEM:
            return "offtopic" if "World Cup" in user.split("Message:")[-1] else "book"
        return await real_text(system, user, **kw)

    monkeypatch.setattr(client, "stream_text", stream_text)
    monkeypatch.setattr(client, "complete_text", complete_text)

    async with signed_in(app) as c:
        r = await c.post("/api/books", files={"file": ("ic.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        try:
            assert (await _wait_ready(c, book_id))["status"] == "ready"
            title = (await c.get(f"/api/books/{book_id}")).json()["title"]
            conv = None

            async def say(message):
                nonlocal conv
                body = {"message": message, **({"conversation_id": conv} if conv else {})}
                ev = _events((await c.post(f"/api/books/{book_id}/chat", json=body)).text)
                conv = next(d["id"] for e, d in ev if e == "conversation")
                return ev

            # Small talk and meta: friendly, about the book, no retrieval, no model answer, never "not found".
            for msg, want in (("hello", "smalltalk"), ("hi there", "smalltalk"), ("thanks!", "smalltalk"),
                              ("what can you do?", "meta")):
                ev = await say(msg)
                text = _answer(ev)
                assert next(d for e, d in ev if e == "done")["intent"] == want, msg
                assert title in text and not any(w in text.lower() for w in NOT_FOUND_WORDS), (msg, text)
                assert not any(e == "sources" for e, _ in ev)
            assert answered == []
            assert _answer(await say("hello")).startswith("Hello! How may I assist you with")

            # A book question: retrieval, then a cited answer from the passages.
            ev = await say("Who keeps the lighthouse?")
            assert next(d for e, d in ev if e == "sources")["sources"] and answered[-1] > 0
            assert next(d for e, d in ev if e == "done")["cited"] == [1]

            # A follow-up is a book question too (rule: "tell me more" with a conversation going).
            ev = await say("tell me more")
            assert any(e == "sources" for e, _ in ev) and next(d for e, d in ev if e == "done")["intent"] == "book_question"

            # Off-topic: polite refusal with example questions, no general-knowledge answer.
            before = len(answered)
            ev = await say("who won the 2018 World Cup?")
            text = _answer(ev)
            assert next(d for e, d in ev if e == "done")["intent"] == "off_topic" and len(answered) == before
            assert "only answer from the book" in text and "France" not in text

            # Not in the book: the model gets passages and says so, with suggestions; no citations.
            ev = await say("What colour is Mara's boat?")
            assert answered[-1] > 0 and _answer(ev).startswith("The book doesn't say.")
            assert next(d for e, d in ev if e == "done")["cited"] == []

            # Nothing retrieved at all: the model is never asked; a polite reply with suggestions instead.
            real_search = chat_api.search_book

            async def nothing(*a, **kw):
                return []

            monkeypatch.setattr(chat_api, "search_book", nothing)
            before = len(answered)
            ev = await say("What did the keeper eat for breakfast?")
            assert len(answered) == before and next(d for e, d in ev if e == "done")["intent"] == "not_found"
            assert "couldn't find anything about that" in _answer(ev)
            monkeypatch.setattr(chat_api, "search_book", real_search)

            # The conversation keeps every turn, so follow-ups have context.
            saved = (await c.get(f"/api/conversations/{conv}")).json()["messages"]
            assert [m["role"] for m in saved][:4] == ["user", "assistant", "user", "assistant"]
            assert saved[1]["meta"]["intent"] == "smalltalk"
        finally:
            await c.delete(f"/api/books/{book_id}")
