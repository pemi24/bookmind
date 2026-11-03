"""Query rewriting: turn a follow-up ("what did he do next?") into a standalone search query."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_list

SYSTEM = """You rewrite a reader's latest question about a book into a single standalone search \
query for a passage search engine. Resolve pronouns and references ("he", "that", "next") using \
the conversation. Keep names and key terms. Output only the query text, nothing else."""


class ExpandOut(BaseModel):
    queries: list[str] = Field(description="2-4 alternative search queries")

    _queries = field_validator("queries", mode="before")(to_list)


# Second chance before answering "the book doesn't say": search again with other wordings.
EXPAND_SYSTEM = """A passage search in a book did not find the answer to a reader's question. Write 3 \
short alternative search queries that could find it: use other names or spellings of the people and \
places involved (e.g. "Abram" for "Abraham"), synonyms, and the words the book itself would likely \
use (older books say "begat", "bare", "wife of"). Keep each query under 12 words."""


def build_expand(question: str, book_title: str) -> str:
    return f"Book: {book_title}\nQuestion: {question}\n\nAlternative search queries:"


def build_user(history: list[tuple[str, str]], question: str) -> str:
    convo = "\n".join(f"{role.upper()}: {text[:600]}" for role, text in history[-6:])
    return f"Conversation so far:\n{convo}\n\nLatest question: {question}\n\nStandalone search query:"
