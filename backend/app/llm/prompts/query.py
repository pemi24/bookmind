"""Query rewriting: turn a follow-up ("what did he do next?") into a standalone search query."""
from __future__ import annotations

SYSTEM = """You rewrite a reader's latest question about a book into a single standalone search \
query for a passage search engine. Resolve pronouns and references ("he", "that", "next") using \
the conversation. Keep names and key terms. Output only the query text, nothing else."""


def build_user(history: list[tuple[str, str]], question: str) -> str:
    convo = "\n".join(f"{role.upper()}: {text[:600]}" for role, text in history[-6:])
    return f"Conversation so far:\n{convo}\n\nLatest question: {question}\n\nStandalone search query:"
