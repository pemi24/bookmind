"""Side-by-side reader: translate numbered paragraphs, keeping them aligned."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_int, to_list, to_str


class ParagraphOut(BaseModel):
    n: int = Field(description="The paragraph's number")
    text: str = Field(description="The paragraph translated")

    _n = field_validator("n", mode="before")(lambda v: to_int(v, 0, 9999, 0))
    _text = field_validator("text", mode="before")(to_str)


class TranslationOut(BaseModel):
    paragraphs: list[ParagraphOut]

    _paragraphs = field_validator("paragraphs", mode="before")(to_list)


def system(language: str) -> str:
    return (f"You translate book text into {language}. Translate every numbered paragraph faithfully and "
            "completely, keeping its meaning, tone and names. Do not summarize, merge or skip paragraphs, and "
            "do not add notes. Return one item per paragraph with the same number.")


def build_user(paragraphs: list[tuple[int, str]], language: str) -> str:
    body = "\n\n".join(f"[{n}]\n{text}" for n, text in paragraphs)
    return f"PARAGRAPHS:\n\n{body}\n\nTranslate each of the {len(paragraphs)} paragraphs into {language}."
