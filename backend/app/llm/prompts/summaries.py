"""Summary prompts (chapter or whole book; short / medium / detailed)."""
from __future__ import annotations

LENGTHS = {
    "short": "3 to 5 sentences in one paragraph.",
    "medium": "2 to 4 paragraphs covering the main events or arguments, key people/ideas and why they matter.",
    "detailed": (
        "A structured Markdown summary: a one-paragraph overview, then '## Key points' as a bulleted list, "
        "then '## Details' with short paragraphs in order, and '## Notable quotes' with 2-3 short verbatim quotes."
    ),
}

SYSTEM = """You summarize books for readers. Use ONLY the text you are given; do not add facts from \
outside knowledge of the book, its author or adaptations. Write in clear, engaging prose. Use \
Markdown. Never mention "the text provided" or "the excerpt"; write as a summary of the book/chapter."""

SPOILER_NOTE = """The reader has only read up to this point. Do not anticipate, foreshadow or hint at \
anything beyond the text given."""


def chapter_user(book_title: str, chapter_title: str, text: str, length: str) -> str:
    return (f"Book: {book_title}\nChapter: {chapter_title}\n\nLength: {LENGTHS[length]}\n\n"
            f"<chapter_text>\n{text}\n</chapter_text>\n\nSummarize this chapter.")


def part_user(book_title: str, chapter_title: str, text: str, part: int, total: int) -> str:
    return (f"Book: {book_title}\nChapter: {chapter_title} (part {part} of {total})\n\n"
            f"<text>\n{text}\n</text>\n\nSummarize this part in one or two dense paragraphs.")


def combine_user(book_title: str, scope: str, pieces: list[tuple[str, str]], length: str, spoiler: bool) -> str:
    body = "\n\n".join(f"### {title}\n{summary}" for title, summary in pieces)
    note = f"\n\n{SPOILER_NOTE}" if spoiler else ""
    return (f"Book: {book_title}\nScope: {scope}\n\nLength: {LENGTHS[length]}{note}\n\n"
            f"<section_summaries>\n{body}\n</section_summaries>\n\n"
            f"Write one coherent summary of the {scope} from these section summaries.")


def book_user(book_title: str, scope: str, text: str, length: str, spoiler: bool) -> str:
    note = f"\n\n{SPOILER_NOTE}" if spoiler else ""
    return (f"Book: {book_title}\nScope: {scope}\n\nLength: {LENGTHS[length]}{note}\n\n"
            f"<book_text>\n{text}\n</book_text>\n\nSummarize the {scope}.")
