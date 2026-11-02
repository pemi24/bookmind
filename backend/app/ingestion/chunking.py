"""Structure-aware chunking.

Chunks never cross chapter boundaries. Inside a chapter the unit is the sentence;
chunks prefer to end at a paragraph break once they reach ~75% of the target size,
and consecutive chunks overlap by roughly `overlap_tokens`.

Every chunk is an exact slice of the chapter text (char_start/char_end), which is
what lets the reader highlight a cited passage precisely.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

CHARS_PER_TOKEN = 4  # good-enough estimate for English; avoids a tokenizer dependency

_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9])")


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


@dataclass
class Unit:
    start: int
    end: int
    para_end: bool

    @property
    def tokens(self) -> int:
        return max(1, round((self.end - self.start) / CHARS_PER_TOKEN))


@dataclass
class ChunkSpan:
    char_start: int
    char_end: int
    text: str
    token_count: int


def _split_long(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Hard-split an overlong sentence at whitespace."""
    out, s = [], start
    while end - s > max_chars:
        cut = s + max_chars
        # back off to the previous space (keep at least half the window)
        space = text.rfind(" ", s + max_chars // 2, cut)
        cut = space + 1 if space != -1 else cut
        out.append((s, cut))
        s = cut
    out.append((s, end))
    return out


def _units(text: str, max_unit_chars: int) -> list[Unit]:
    units: list[Unit] = []
    for m in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):  # paragraphs separated by blank lines
        p_start, p_end = m.start(), m.end()
        sent_starts = [p_start] + [p_start + s.end() for s in _SENTENCE_END.finditer(m.group())]
        bounds = list(zip(sent_starts, sent_starts[1:] + [p_end]))
        for k, (s, e) in enumerate(bounds):
            pieces = _split_long(text, s, e, max_unit_chars) if e - s > max_unit_chars else [(s, e)]
            for j, (ps, pe) in enumerate(pieces):
                last = k == len(bounds) - 1 and j == len(pieces) - 1
                units.append(Unit(ps, pe, para_end=last))
    return units


def chunk_text(
    text: str,
    target_tokens: int = 500,
    max_tokens: int = 700,
    overlap_tokens: int = 80,
) -> list[ChunkSpan]:
    if not text.strip():
        return []
    units = _units(text, max_unit_chars=max_tokens * CHARS_PER_TOKEN)
    spans: list[tuple[int, int]] = []  # (first_unit, last_unit) inclusive
    i, n = 0, len(units)
    while i < n:
        first, tokens = i, 0
        while i < n:
            t = units[i].tokens
            if tokens and tokens + t > max_tokens:
                break
            tokens += t
            i += 1
            if tokens >= target_tokens or (units[i - 1].para_end and tokens >= 0.75 * target_tokens):
                break
        spans.append((first, i - 1))
        if i >= n:
            break
        # Step back to create overlap, but always make forward progress.
        back, ov = i, 0
        while back - 1 > first and ov < overlap_tokens:
            back -= 1
            ov += units[back].tokens
        i = back if ov <= max(overlap_tokens * 2, 1) else i

    # Fold a tiny tail into the previous chunk when it still fits.
    if len(spans) >= 2:
        f, l = spans[-1]
        tail = sum(u.tokens for u in units[f : l + 1])
        pf, pl = spans[-2]
        if tail < 0.25 * target_tokens and units[l].end - units[pf].start <= max_tokens * 1.2 * CHARS_PER_TOKEN:
            spans[-2] = (pf, l)
            spans.pop()

    out = []
    for f, l in spans:
        s, e = units[f].start, units[l].end
        chunk = text[s:e]
        out.append(ChunkSpan(char_start=s, char_end=e, text=chunk, token_count=estimate_tokens(chunk)))
    return out


def page_at(page_map: list[list[int]], offset: int) -> int | None:
    """Page number containing character `offset`, given [[offset, page], ...]."""
    if not page_map:
        return None
    idx = bisect.bisect_right([o for o, _ in page_map], offset) - 1
    return page_map[max(idx, 0)][1]
