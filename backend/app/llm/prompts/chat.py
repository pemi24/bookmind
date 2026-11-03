"""Prompts for grounded question answering. Tune wording here, not in the API code."""
from __future__ import annotations

import re
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
# Refusals were too frequent when a passage held the answer only implicitly (e.g. "Hannah ... called
# his name Samuel" for "who was Samuel's mother?"), so the rules allow combining and inferring from
# the passages and giving partial answers; only a question nothing relevant speaks to is refused.
SYSTEM = """You are BookMind, a helpful reading assistant. You answer questions about a book using the numbered passages from the book that come with each question.
- Base the answer on the passages. You may combine details from several passages and draw clear conclusions from them (for example, "Hannah bare a son, and called his name Samuel" shows that Hannah is Samuel's mother).
- Do not add facts that no passage supports, even if you know the book.
- If the passages answer only part of the question, give that part and say what they don't show.
- After each sentence, write the number of the passage it comes from in brackets, like [1].
- Be concise (2-5 sentences). Markdown is fine.
- Earlier messages only help you understand follow-up questions ("he", "next")."""

NOT_FOUND = "The book doesn't say."

INSTRUCTION = ("Answer the question using the passages above, in 2-4 sentences. After each sentence put the "
               "number of the passage it comes from in brackets, for example: "
               "\"Alice follows the White Rabbit down a rabbit-hole [2].\" "
               f"Only if none of the passages is relevant to the question, answer: \"{NOT_FOUND}\"")

OVERVIEW_RULE = """
About the book (for questions about the book as a whole, such as what it is about or who the main \
characters are; combine this with the passages): "{title}"{author}.
{summary}Chapters: {chapters}"""

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


def build_overview(title: str, author: str | None, chapter_titles: Sequence[str], summary: str | None = None,
                   max_chars: int = 2500) -> str:
    """Title, author, chapter list (and a saved book summary, if any) for whole-book questions."""
    chapters = "; ".join(f"{i}. {t}" for i, t in enumerate(chapter_titles, start=1))
    if len(chapters) > max_chars:
        chapters = chapters[:max_chars].rsplit(";", 1)[0] + "; …"
    summary_line = f"Summary: {summary.strip()[:1500]}\n" if summary else ""
    return OVERVIEW_RULE.format(title=title, author=f" by {author}" if author else "", summary=summary_line,
                                chapters=chapters or "(none)")


def build_system(
    style: str = "default",
    spoiler: tuple[int, str] | None = None,
    compare: bool = False,
    persona: str | None = None,
    overview: str | None = None,
) -> str:
    parts = [SYSTEM]
    if overview:
        parts.append(overview)
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


_NOT_FOUND = re.compile(
    r"(?:does|do|did)(?:n't| not) (?:say|state|mention|tell|specify|name|reveal|contain|include|provide|give"
    r"|show|indicate|identify|explain)"
    r"|(?:could|can)(?:n't| ?not) find|not (?:mentioned|stated|specified|named|given|provided|found)"
    r"|no (?:information|mention|passage)|nothing (?:about|on|in the)|isn't (?:mentioned|stated|given)"
)


def is_not_found(answer: str) -> bool:
    """A short 'the book doesn't say' style answer (its stray [n] markers are not real citations).

    Models word it many ways ("The provided passages do not state who ..."), so match the idea, not one
    phrase, in the opening sentence. Answers that give something and then note a gap ("X is Samuel's
    mother; the passages don't state her age, but ...") are real answers.
    """
    a = re.sub(r"\[[\d,\s–-]+\]", "", answer).strip().lower().replace("’", "'")
    first = re.split(r"(?<=[.!?])\s", a, maxsplit=1)[0]
    if len(a) >= 200 or len(first) > 140 or re.search(r";|\bbut\b|\bhowever\b|\balthough\b", first):
        return False
    return bool(_NOT_FOUND.search(first))


def admits_gap(answer: str) -> bool:
    """A refusal, or a short answer that says the passages don't show something ("However, the passages
    do not show who ..."): worth searching again before settling for it."""
    a = re.sub(r"\[[\d,\s–-]+\]", "", answer).lower().replace("’", "'")
    return is_not_found(answer) or (len(a) < 500 and bool(_NOT_FOUND.search(a)))
