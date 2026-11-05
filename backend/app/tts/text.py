"""Turning text into something that sounds natural read aloud, one sentence at a time.

clean_for_speech() strips what shouldn't be spoken from an AI reply (markdown, citation markers,
URLs, emoji). split_sentences() cuts text into sentences and keeps each one's character offsets,
so the reader can highlight the sentence being read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CODE_BLOCK = re.compile(r"```.*?(?:```|$)", re.S)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
# [3], [1, 2], [2-4], [1–3; 5]: the answers' passage markers
_CITATION = re.compile(r"\s*\[\d+(?:\s*[,;–-]\s*\d+)*\]")
# A URL never ends with the sentence's own punctuation ("see https://x.org."), but may end with a
# bracketed part of its own (Wikipedia's ".../Fox_(novel)").
_URL = re.compile(r"\b(?:https?://|www\.)(?:\([^\s()]*\)|[^\s<>()])*(?:\([^\s()]*\)|[^\s<>().,;:!?'\"\]])", re.I)
_EMPTY_BRACKETS = re.compile(r"\s*(?:\(\s*\)|\[\s*\])")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF☀-➿⬀-⯿⌀-⏿️‍⃣]+"
)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_LINE_MARKER = re.compile(r"^\s*(?:#{1,6}\s+|>\s?|[-*+•]\s+|\d+[.)]\s+)")
_RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$|^\s*\|?\s*:?-{3,}.*$")
_EMPHASIS = re.compile(r"(\*{1,3}|(?<!\w)_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)")
_TERMINAL = re.compile(r"[.!?…:;]['\"”’)\]]*$")


def clean_for_speech(markdown: str) -> str:
    """Plain, speakable text from a markdown reply. Lists and headings get a full stop so they're
    read as separate phrases instead of running into each other."""
    text = _CODE_BLOCK.sub(" ", markdown)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _CITATION.sub("", text)
    text = _URL.sub("", text)
    text = _EMPTY_BRACKETS.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _EMOJI.sub("", text)
    lines = []
    for line in text.splitlines():
        if _RULE.match(line):
            continue
        line = _LINE_MARKER.sub("", line)
        line = line.replace("|", ", ").replace("`", "")
        for _ in range(2):  # **_nested_** emphasis
            line = _EMPHASIS.sub(r"\2", line)
        line = re.sub(r"\s+", " ", line)
        line = re.sub(r" ([.,;:!?])", r"\1", line).strip(" ,")  # left behind by a removed URL or emoji
        if line:
            lines.append(line if _TERMINAL.search(line) else line + ".")
    return " ".join(lines)


@dataclass
class Sentence:
    start: int  # offsets into the text given to split_sentences()
    end: int
    text: str  # what to speak: the slice with its whitespace tidied


# Words that end with a full stop without ending the sentence.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "st", "prof", "sr", "jr", "vs", "etc", "e.g", "i.e", "cf", "no", "vol", "ch",
    "p", "pp", "fig", "gen", "col", "capt", "lt", "rev", "hon", "mt", "jan", "feb", "mar", "apr", "aug",
    "sept", "sep", "oct", "nov", "dec", "approx", "dept", "est", "inc", "ltd", "co", "messrs", "mme", "mlle",
}
_BOUNDARY = re.compile(r"[.!?…]+['\"”’)\]]*(?=\s)|\n\s*\n")
_WORD_BEFORE = re.compile(r"([\w.]+)$")
_NEXT_START = re.compile(r"\s*['\"“‘(\[]?[\w¿¡]")


def _is_abbreviation(text: str, dot: int) -> bool:
    # only the word just before the dot: searching from the text's start made long chapters slow
    m = _WORD_BEFORE.search(text, max(0, dot - 40), dot)
    if not m:
        return False
    word = m.group(1).lower().rstrip(".")
    # single letters are initials ("J. R. R. Tolkien"), but "I." ends a sentence often enough
    return word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha() and word != "i")


def split_sentences(text: str, max_chars: int = 300) -> list[Sentence]:
    """Sentences with their offsets. Paragraph breaks always end one; a sentence longer than
    max_chars is cut at a comma, semicolon or dash (else a space) so each piece starts quickly."""
    out: list[Sentence] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end()
        if not m.group().startswith("\n"):
            if text[m.start()] == "." and _is_abbreviation(text, m.start()):
                continue
            # "...and so on." followed by lowercase: an ellipsis or abbreviation mid-sentence
            nxt = _NEXT_START.match(text, end)
            if nxt and nxt.group()[-1].islower():
                continue
        _add(text, start, end, max_chars, out)
        start = end
    _add(text, start, len(text), max_chars, out)
    return out


def _add(text: str, start: int, end: int, max_chars: int, out: list[Sentence]) -> None:
    # trim surrounding whitespace, keeping offsets exact
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    while end - start > max_chars:
        piece = text[start:start + max_chars]
        cut = max(piece.rfind(", "), piece.rfind("; "), piece.rfind(": "), piece.rfind(" — "), piece.rfind(" – "))
        if cut < max_chars // 3:
            cut = piece.rfind(" ")
        if cut <= 0:
            cut = max_chars - 1
        _emit(text, start, start + cut + 1, out)
        start += cut + 1
        while start < end and text[start].isspace():
            start += 1
    _emit(text, start, end, out)


def _emit(text: str, start: int, end: int, out: list[Sentence]) -> None:
    spoken = re.sub(r"\s+", " ", text[start:end]).strip()
    if any(c.isalnum() for c in spoken):  # skip stray punctuation and decorations ("* * *")
        out.append(Sentence(start, end, spoken))
