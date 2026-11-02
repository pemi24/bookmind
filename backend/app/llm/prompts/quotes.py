"""Quote finder: pick exact verbatim quotes about a topic from retrieved passages."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_int, to_list, to_str


class QuoteOut(BaseModel):
    passage: int = Field(description="Number of the passage the quote comes from")
    quote: str = Field(description="Copied EXACTLY, character for character, from that passage (1-4 sentences)")
    note: str = Field(description="One short sentence on how it relates to the topic")

    _passage = field_validator("passage", mode="before")(lambda v: to_int(v, 0, 999, 0))
    _note = field_validator("note", mode="before")(to_str)


class QuotesOut(BaseModel):
    quotes: list[QuoteOut]

    _quotes = field_validator("quotes", mode="before")(to_list)


SYSTEM = """You find quotations in a book. Pick sentences from the numbered passages that are about \
the reader's topic and copy them EXACTLY: same words and punctuation, no "...", no paraphrase. If \
nothing is relevant, return an empty list."""


def build_user(topic: str, passages: list[str], limit: int) -> str:
    ps = "\n\n".join(f"[{i}]\n{p}" for i, p in enumerate(passages, 1))
    return f"PASSAGES:\n\n{ps}\n\nTopic: {topic}\nReturn up to {limit} exact quotes about this topic."
