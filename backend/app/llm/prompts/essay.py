"""Essay helper: an outline for the reader's thesis, supported by exact quotes from the book."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_int, to_list, to_str


class EvidenceOut(BaseModel):
    passage: int = Field(description="Number of the passage the quote comes from")
    quote: str = Field(description="Copied EXACTLY, character for character, from that passage (1-3 sentences)")
    explanation: str = Field(description="One sentence: how this quote supports the point")

    _passage = field_validator("passage", mode="before")(lambda v: to_int(v, 0, 999, 0))
    _explanation = field_validator("explanation", mode="before")(to_str)


class SectionOut(BaseModel):
    heading: str = Field(description="Short heading for this body section")
    point: str = Field(description="The argument this section makes, in 1-2 sentences")
    evidence: list[EvidenceOut]

    _heading = field_validator("heading", "point", mode="before")(to_str)
    _evidence = field_validator("evidence", mode="before")(to_list)


class EssayOut(BaseModel):
    title: str = Field(description="A working title for the essay")
    thesis: str = Field(description="The thesis, sharpened into one clear, arguable sentence")
    introduction: str = Field(description="2-3 sentences on how to open the essay")
    sections: list[SectionOut]
    counterargument: str = Field(description="The strongest objection, and how to answer it (2-3 sentences)")
    conclusion: str = Field(description="2-3 sentences on how to close the essay")

    _text = field_validator("title", "thesis", "introduction", "counterargument", "conclusion", mode="before")(to_str)
    _sections = field_validator("sections", mode="before")(to_list)


SYSTEM = """You help a student plan an essay about a book. Using ONLY the numbered passages from the \
book, build an outline that argues the student's thesis. Support each section with quotes copied \
EXACTLY from the passages: same words and punctuation, no "...", no paraphrase. If the passages \
don't support part of the thesis, say so in the section's point instead of inventing evidence."""


def build_user(book_title: str, thesis: str, passages: list[str], sections: int) -> str:
    ps = "\n\n".join(f"[{i}]\n{p}" for i, p in enumerate(passages, 1))
    return (f"BOOK: {book_title}\n\nPASSAGES:\n\n{ps}\n\nThesis: {thesis}\n\n"
            f"Write an outline with {sections} body sections, each with 1-3 exact quotes as evidence.")
