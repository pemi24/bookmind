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
SYSTEM = """You are BookMind, a friendly, knowledgeable reading companion for {book}. You answer the reader's questions about this book using the numbered passages from it that come with each question.
- Be warm and conversational in tone, but every factual claim about the book must come only from the provided passages (and the book memory, when given). Never use outside knowledge about the book, its author or its subject.
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
               f"Only if none of the passages is relevant to the question, start with \"{NOT_FOUND}\" and then "
               "suggest one or two related questions the passages could answer.")

OVERVIEW_RULE = """
Book memory: "{title}"{author}. Use it to understand the whole story (who, what, in which order, \
why), for questions about the book as a whole and for context the passages leave out. Cite the \
numbered passages for details and quotes; when something comes only from this memory, say which \
chapter it is from instead of a [n].
{summary}Chapter by chapter:
{chapters}"""

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


def _first_sentence(text: str, limit: int = 220) -> str:
    s = re.split(r"(?<=[.!?])\s", " ".join(text.split()), maxsplit=1)[0]
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def _chapter_lines(chapters: Sequence[tuple[str, str | None]], max_chars: int) -> str:
    """Full chapter memories if they fit; else first sentences; else titles only (cut off at the end)."""
    for shorten in (lambda m: " ".join(m.split()), _first_sentence, None):
        lines = [f"{i}. {t}" + (f": {shorten(m)}" if shorten and m else "")
                 for i, (t, m) in enumerate(chapters, start=1)]
        text = "\n".join(lines)
        if len(text) <= max_chars or shorten is None:
            break
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n…"
    return text or "(none)"


def build_overview(title: str, author: str | None, chapters: Sequence[tuple[str, str | None]],
                   summary: str | None = None, max_chars: int = 14000) -> str:
    """Book memory for the prompt: title, author, a saved whole-book summary (if any) and each chapter
    with its memory summary (chapters still without one are listed by title)."""
    summary_line = f"Book summary: {_first_sentence(summary, 1500) if len(summary) > 1500 else summary.strip()}\n" \
        if summary else ""
    return OVERVIEW_RULE.format(title=title, author=f" by {author}" if author else "", summary=summary_line,
                                chapters=_chapter_lines(chapters, max(max_chars - len(summary_line), 300)))


def build_system(
    style: str = "default",
    spoiler: tuple[int, str] | None = None,
    compare: bool = False,
    persona: str | None = None,
    overview: str | None = None,
    book_title: str | None = None,
    author: str | None = None,
) -> str:
    book = f'"{book_title}"' + (f" by {author}" if author else "") if book_title else "the selected book"
    parts = [SYSTEM.format(book=book)]
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


MEMORY_INSTRUCTION = ("Answer the question using the passages above together with the book memory (the "
                      "chapter-by-chapter summaries in your instructions), in 2-5 sentences. For questions about the "
                      "whole book or how things develop, build the answer from the book memory and back it with "
                      "passages where they fit. Put the passage number in brackets after sentences that use a "
                      "passage, for example: \"Alice follows the White Rabbit down a rabbit-hole [2].\" "
                      f"Only if neither the passages nor the book memory are relevant, start with \"{NOT_FOUND}\" "
                      "and then suggest one or two related questions they could answer.")


def build_user_turn(question: str, passages: Sequence[Passage], memory: bool = False) -> str:
    """The question with its passages. `memory`: the system prompt carries a book memory, so say to use it
    too (otherwise small and "lite" models answer from the passages alone and miss the bigger picture)."""
    if not passages and not memory:
        return f"(No passages were found.)\n\nQuestion: {question}\n\nReply exactly: \"{NOT_FOUND}\""
    body = format_passages(passages) if passages else "(No passages were found.)"
    return f"{body}\n\nQuestion: {question}\n\n{MEMORY_INSTRUCTION if memory else INSTRUCTION}\n\nAnswer:"


_NOT_FOUND = re.compile(
    r"(?:does|do|did)(?:n't| not) (?:say|state|mention|tell|specify|name|reveal|contain|include|provide|give"
    r"|show|indicate|identify|explain|describe|discuss|cover|detail)"
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


def _total(system: str, messages: Sequence[dict]) -> int:
    return len(system) + sum(len(m["content"]) for m in messages)


def fit_chat(system: str, messages: list[dict], max_chars: int) -> tuple[str, list[dict]]:
    """Shrink a chat request to fit a provider with a small request limit (e.g. Groq's free plan).

    In order, until it fits: shorten the book memory to first sentences, then to chapter titles;
    drop the oldest conversation turns; drop the last (lowest-ranked) passages, keeping at least 3.
    Raises ValueError if it still doesn't fit (e.g. a long chapter sent for summarizing).
    """
    messages = [dict(m) for m in messages]
    if _total(system, messages) <= max_chars:
        return system, messages

    head, sep, chapters = system.partition("Chapter by chapter:\n")
    if sep:
        lines = chapters.split("\n")
        for shorten in (lambda line: _shorten_memory_line(line, sentence=True),
                        lambda line: _shorten_memory_line(line, sentence=False)):
            system = head + sep + "\n".join(shorten(ln) for ln in lines)
            if _total(system, messages) <= max_chars:
                return system, messages

    while len(messages) > 1 and _total(system, messages) > max_chars:
        messages.pop(0)  # oldest turn first; the question itself is last

    last = messages[-1]["content"]
    blocks = re.split(r"\n\n(?=\[\d+\] \()", last)
    if blocks[0].startswith("PASSAGES FROM THE BOOK:") and len(blocks) > 1:
        passages, tail = blocks[:-1], blocks[-1]
        # The last block holds the last passage followed by the question: split it back apart.
        last_passage, _, question = tail.partition("\n\nQuestion: ")
        passages.append(last_passage)
        while len(passages) > 4 and _total(system, messages[:-1]) + len("\n\n".join(passages)) + len(question) + 20 > max_chars:
            passages.pop()
        messages[-1] = {**messages[-1], "content": "\n\n".join(passages) + "\n\nQuestion: " + question}
    if _total(system, messages) > max_chars:
        raise ValueError("request too large for this provider")
    return system, messages


def _shorten_memory_line(line: str, sentence: bool) -> str:
    m = re.match(r"^(\d+\. .*?): (.+)$", line)
    if not m:
        return line
    return f"{m.group(1)}: {_first_sentence(m.group(2), 160)}" if sentence else m.group(1)
