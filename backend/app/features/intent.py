"""Route each chat message before any retrieval: small talk, questions about the assistant,
book questions, or off-topic questions (see llm/prompts/intent.py for the rules and replies).

Order: rules for obvious messages; follow-ups and messages that mention the book go straight to
the book; otherwise one short classification call on the light model. Failure or doubt means
"book_question", so a book question is never mistaken for small talk. An "off_topic" verdict is
double-checked against the book itself by the caller (see OFF_TOPIC_MAX_RELEVANCE).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.llm import client as llm
from app.llm.prompts import intent as P

log = logging.getLogger(__name__)

# An "off_topic" message whose best passage scores at least this (re-ranker, 0-1) is about the book after all.
OFF_TOPIC_MAX_RELEVANCE = 0.3


@dataclass(frozen=True)
class Route:
    intent: str  # smalltalk | meta | book_question | off_topic
    kind: str = ""  # smalltalk flavour (greeting, thanks...) for the reply
    by: str = "rule"  # rule | model | default


async def route(message: str, history: list[dict], book_title: str) -> Route:
    if hit := P.rule_intent(message):
        return Route(*hit)
    if history and P.is_follow_up(message):
        return Route("book_question", by="rule")  # "tell me more", "why did he do that?"
    if P.mentions_book(message, book_title):
        return Route("book_question", by="rule")
    try:
        reply = await llm.complete_text(
            P.CLASSIFY_SYSTEM,
            P.build_classify_user(book_title, [(m["role"], m["content"]) for m in history], message),
            model=llm.provider().fast_model, effort="low", max_tokens=60,
        )
    except llm.LLMError as e:
        log.warning("Intent classification failed, treating as a book question: %s", e.message)
        return Route("book_question", by="default")
    intent = P.parse_intent(reply)
    # A short reply to the assistant's own question ("yes", "sure", "the second one") continues the
    # book conversation; it isn't small talk.
    last = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    if intent == "smalltalk" and last.rstrip().endswith("?") and len(message.split()) <= 4:
        intent = "book_question"
    return Route(intent, "ack" if intent == "smalltalk" else "", by="model")
