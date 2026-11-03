"""SQLAlchemy ORM models.

Every table that belongs to a book has `book_id ... ON DELETE CASCADE`, so deleting a
book removes all derived data in one statement.
"""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


def _book_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)


class AppMeta(Base):
    """Key/value facts about the schema (e.g. embedding dimension) checked at startup."""

    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(10))
    file_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    pages_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_fiction: Mapped[bool | None] = mapped_column(Boolean)
    # pending | processing | ready | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    status_message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    suggested_questions: Mapped[list] = mapped_column(JSONB, default=list)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reading progress (chapter positions survive re-indexing; chapter ids don't).
    reading_position: Mapped[int | None] = mapped_column(Integer)  # chapter the reader is on
    reading_offset: Mapped[int | None] = mapped_column(Integer)  # char offset of the paragraph at the top
    furthest_position: Mapped[int | None] = mapped_column(Integer)  # furthest chapter actually read
    reading_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="book", order_by="Chapter.position", passive_deletes=True
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    position: Mapped[int] = mapped_column(Integer)  # 1-based reading order
    title: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)  # cleaned full text (reader + highlighting)
    # [[char_offset, page_number], ...] — page that starts at each offset
    page_map: Mapped[list] = mapped_column(JSONB, default=list)
    start_page: Mapped[int | None] = mapped_column(Integer)
    end_page: Mapped[int | None] = mapped_column(Integer)

    book: Mapped[Book] = relationship(back_populates="chapters")
    __table_args__ = (Index("ix_chapters_book_position", "book_id", "position"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    # Denormalised so the spoiler guard is a cheap WHERE clause.
    chapter_position: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)  # global order within the book
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)  # offsets into chapters.text
    char_end: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))

    __table_args__ = (
        Index("ix_chunks_book_position", "book_id", "position"),
        Index("ix_chunks_book_chapter_pos", "book_id", "chapter_position"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Primary book. Compare-mode conversations list all books in book_ids.
    book_id: Mapped[int] = _book_fk()
    book_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    mode: Mapped[str] = mapped_column(String(20), default="chat")  # chat | persona | compare
    persona: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)  # style, spoiler limit, rewritten query...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    citations: Mapped[list[Citation]] = relationship(
        order_by="Citation.marker", passive_deletes=True, lazy="selectin"
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    marker: Mapped[int] = mapped_column(Integer)  # the [n] used in the answer
    score: Mapped[float | None] = mapped_column(Float)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note | answer | passage | quote
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    location: Mapped[dict] = mapped_column(JSONB, default=dict)  # chapter/page labels for export
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list)
    color: Mapped[str | None] = mapped_column(String(20))  # reader highlight colour
    comment: Mapped[str | None] = mapped_column(Text)  # the reader's own words on a highlight
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Summary(Base):
    """Cache of generated summaries (chapter_id NULL = whole book)."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    length: Mapped[str] = mapped_column(String(20))  # short | medium | detailed
    # Whole-book summaries respect the spoiler guard: summary of chapters 1..up_to_chapter (NULL = all).
    up_to_chapter: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_summaries_lookup", "book_id", "chapter_id", "length", "up_to_chapter"),)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    # [{type, question, options?, answer, explanation, chunk_id}]
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    best_score: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[list] = mapped_column(JSONB, default=list)  # [{score, total, at}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    # SM-2 spaced repetition state
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    kind: Mapped[str] = mapped_column(String(20))  # character | place | term | theme | concept
    name: Mapped[str] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(300)), default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    # What each chapter reveals: [{"chapter": position, "text": ...}] — filtered by the spoiler guard.
    details: Mapped[list] = mapped_column(JSONB, default=list)
    first_chapter: Mapped[int | None] = mapped_column(Integer)  # chapter position (spoiler guard)
    importance: Mapped[int] = mapped_column(Integer, default=1)  # 1..5
    chunk_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)

    __table_args__ = (Index("ix_entities_book_kind", "book_id", "kind"),)


class EntityRelation(Base):
    __tablename__ = "entity_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    source_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    first_chapter: Mapped[int | None] = mapped_column(Integer)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    when_label: Mapped[str | None] = mapped_column(String(200))  # in-story time if known
    chapter_position: Mapped[int | None] = mapped_column(Integer)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    importance: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (Index("ix_timeline_book_position", "book_id", "position"),)


class FeatureJob(Base):
    """Status of long-running per-book LLM jobs (entities, timeline...) so the UI can poll."""

    __tablename__ = "feature_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = _book_fk()
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_feature_jobs_book_kind", "book_id", "kind"),)
