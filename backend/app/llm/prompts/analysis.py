"""Per-chapter analysis: entities, relationships and key events (powers Explorer + Timeline)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_enum, to_int, to_list, to_str

EntityKind = Literal["character", "place", "organization", "term", "concept", "theme"]
_KINDS = ("character", "place", "organization", "term", "concept", "theme")
_KIND_SYNONYMS = {
    "person": "character", "people": "character", "animal": "character", "creature": "character",
    "figure": "character", "author": "character", "location": "place", "setting": "place", "city": "place",
    "country": "place", "building": "place", "group": "organization", "institution": "organization",
    "faction": "organization", "army": "organization", "company": "organization", "object": "term",
    "item": "term", "thing": "term", "artifact": "term", "word": "term", "idea": "concept",
    "principle": "concept", "topic": "theme", "motif": "theme", "event": "concept",
}


class EntityOut(BaseModel):
    name: str = Field(description="Canonical name; reuse the exact known name if this entity was seen before")
    kind: EntityKind
    aliases: list[str] = Field(description="Other names/titles used in THIS chapter")
    description: str = Field(description="1-2 sentences: what THIS chapter reveals about it (no later events)")
    importance: int = Field(description="5 = central to the book so far, 1 = passing mention (integer 1-5)")

    _kind = field_validator("kind", mode="before")(lambda v: to_enum(v, _KINDS, _KIND_SYNONYMS, "term"))
    _aliases = field_validator("aliases", mode="before")(lambda v: [str(a) for a in to_list(v)])
    _description = field_validator("description", mode="before")(to_str)
    _importance = field_validator("importance", mode="before")(lambda v: to_int(v, 1, 5, 2))


class RelationOut(BaseModel):
    source: str = Field(description="Entity name (must match an entity name)")
    target: str = Field(description="Entity name (must match an entity name)")
    relation: str = Field(description="Short label, e.g. 'sister of', 'serves', 'is a type of', 'causes'")
    description: str = Field(description="One short sentence")

    _description = field_validator("description", mode="before")(to_str)


class EventOut(BaseModel):
    title: str = Field(description="Short event title (max ~8 words)")
    description: str = Field(description="1-2 sentences")
    when: str | None = Field(description="In-story or historical time if the text states it")
    importance: int = Field(description="integer 1-5, 5 = most important")
    evidence: str = Field(description="A SHORT verbatim phrase (5-15 words) copied exactly from the chapter")

    _description = field_validator("description", "evidence", mode="before")(to_str)
    _when = field_validator("when", mode="before")(lambda v: (str(v).strip() or None) if v not in (None, "null") else None)
    _importance = field_validator("importance", mode="before")(lambda v: to_int(v, 1, 5, 3))


class ChapterAnalysis(BaseModel):
    entities: list[EntityOut]
    relations: list[RelationOut]
    events: list[EventOut]

    _lists = field_validator("entities", "relations", "events", mode="before")(to_list)


SYSTEM = """You extract knowledge from ONE chapter of a book for a reader's glossary, relationship \
map and timeline. Use only this chapter's text. Describe things as of this chapter; never mention \
later events. Be selective: the entities that matter (not every noun) and the 3-8 key events."""

FICTION_GUIDE = """Fiction. Entities: characters, places, groups, important objects/terms, themes. \
Relations: between characters (family, friend, enemy, serves, loves...) or character-place/group. \
Events: plot events in story order."""

NONFICTION_GUIDE = """Non-fiction. Entities: concepts, terms, people, places, organizations, themes. \
Relations form a concept map ('part of', 'causes', 'contrasts with', 'example of'...). Events: \
historical events or the key steps of the argument, in order."""


def build_user(book_title: str, is_fiction: bool | None, known: list[str], chapter_title: str, text: str) -> str:
    guide = NONFICTION_GUIDE if is_fiction is False else FICTION_GUIDE
    known_txt = ", ".join(known[:80]) if known else "(none yet)"
    return (f"Book: {book_title}\n{guide}\nKnown names (reuse these exact spellings): {known_txt}\n\n"
            f"Chapter: {chapter_title}\nCHAPTER TEXT:\n{text}\n\n"
            "Return the entities, relations (between names in your entities list) and events. "
            "Each event's evidence must be copied word for word from the chapter text.")
