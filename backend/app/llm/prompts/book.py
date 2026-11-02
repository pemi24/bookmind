"""Book-level prompts run after indexing (genre + suggested starter questions)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_list

SYSTEM = """You help readers start a book. From its title, chapter list and sample passages, decide \
whether it is fiction and write 6-8 interesting, varied questions this book's text can answer \
(plot, characters, ideas, arguments). Don't spoil the ending in the questions."""


class BookProfile(BaseModel):
    is_fiction: bool = Field(description="True for novels, stories, plays, poetry; false otherwise")
    questions: list[str] = Field(description="6 to 8 starter questions")

    _questions = field_validator("questions", mode="before")(
        lambda v: [str(q).strip() for q in to_list(v) if str(q).strip()])


def build_user(title: str, author: str | None, chapters: list[str], samples: list[str]) -> str:
    ch = "\n".join(f"- {c}" for c in chapters[:60])
    smp = "\n\n---\n\n".join(s[:1200] for s in samples)
    return f"Title: {title}\nAuthor: {author or 'unknown'}\n\nChapters:\n{ch}\n\nSample passages:\n{smp}"
