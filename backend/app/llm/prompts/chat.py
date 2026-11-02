"""Prompts for grounded question answering. Tune wording here, not in the API code."""
from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.hybrid import Passage

STYLES = {
    "default": "",
    "eli5": "Explain like the reader is 10 years old: short sentences, everyday words, no jargon.",
    "student": "Explain for a high-school or university student: clear structure, define key terms, "
               "point out what matters for understanding the book.",
    "expert": "Answer for an expert reader: precise, dense, discuss nuance, themes and textual detail.",
    "analogy": "Explain using one vivid, accurate analogy from everyday life, then tie it back to the text.",
}

# Wording tuned on a 3B local model (qwen2.5:3b): plain rules, the question right after the
# passages, then the instruction with a concrete example and a short refusal phrase. Telling a small
# model "if not found, say X" up front made it answer X to everything.
SYSTEM = """You are BookMind, a helpful reading assistant. You answer questions about a book using the numbered passages from the book that come with each question.
- Answer from the passages. Do not add facts that are not in them, even if you know the book.
- After each sentence, write the number of the passage it comes from in brackets, like [1].
- Be concise (2-5 sentences). Markdown is fine.
- Earlier messages only help you understand follow-up questions ("he", "next")."""

NOT_FOUND = "The book doesn't say."

INSTRUCTION = ("Answer the question using the passages above, in 2-4 sentences. After each sentence put the "
               "number of the passage it comes from in brackets, for example: "
               "\"Alice follows the White Rabbit down a rabbit-hole [2].\" "
               f"If the passages say nothing about the question, answer: \"{NOT_FOUND}\"")

SPOILER_RULE = """
Spoiler guard: the reader has only read up to chapter {n} ("{title}"). The passages are limited to \
that point. Do not reveal, hint at or speculate about anything that happens later in the book. If \
the question asks about later events, say they haven't reached that part yet."""

COMPARE_RULE = """
This is a comparison across several books. Passages are labelled with their book. Address each \
book separately where relevant, then compare. Cite passages from each book."""

PERSONA_RULE = """
Persona mode: answer in the first person as {name}, a character in this book, in their voice, \
vocabulary and attitude as shown in the passages. Stay faithful to the book: only claim what the \
passages support, still cite passages with [n], and if {name} wouldn't know something (or the \
passages don't say), answer in character that you don't know. Never break character except to \
say something isn't in the book."""


def build_system(
    style: str = "default",
    spoiler: tuple[int, str] | None = None,
    compare: bool = False,
    persona: str | None = None,
) -> str:
    parts = [SYSTEM]
    if compare:
        parts.append(COMPARE_RULE)
    if persona:
        parts.append(PERSONA_RULE.format(name=persona))
    if spoiler:
        parts.append(SPOILER_RULE.format(n=spoiler[0], title=spoiler[1]))
    if STYLES.get(style):
        parts.append("\nAnswer style: " + STYLES[style])
    return "\n".join(parts)


def format_passages(passages: Sequence[Passage]) -> str:
    """Passages labelled exactly the way they must be cited: [1], [2]... (book named only in compare mode)."""
    multi_book = len({p.book_id for p in passages}) > 1
    blocks = []
    for i, p in enumerate(passages, start=1):
        pages = ""
        if p.page_start:
            pages = f", p. {p.page_start}" + (f"-{p.page_end}" if p.page_end and p.page_end != p.page_start else "")
        where = f"{p.book_title} — {p.chapter_title}" if multi_book else p.chapter_title
        blocks.append(f"[{i}] ({where}{pages})\n{p.text}")
    return "PASSAGES FROM THE BOOK:\n\n" + "\n\n".join(blocks)


def build_user_turn(question: str, passages: Sequence[Passage]) -> str:
    if not passages:
        return f"(No passages were found.)\n\nQuestion: {question}\n\nReply exactly: \"{NOT_FOUND}\""
    return f"{format_passages(passages)}\n\nQuestion: {question}\n\n{INSTRUCTION}\n\nAnswer:"


def is_not_found(answer: str) -> bool:
    """A short 'the book doesn't say' style answer (its stray [n] markers are not real citations)."""
    a = answer.strip().lower()
    return len(a) < 160 and any(k in a for k in ("doesn't say", "does not say", "couldn't find", "could not find",
                                                  "not mentioned", "doesn't mention", "does not mention"))
