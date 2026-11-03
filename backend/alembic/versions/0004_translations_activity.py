"""chapter translations (side-by-side reader) and daily activity (reading stats)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        # One entry per chapter paragraph (chapter.text split on blank lines), aligned by index.
        sa.Column("paragraphs", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chapter_id", "language", name="uq_translations_chapter_language"),
    )
    op.create_table(
        "activity_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("read_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cards_reviewed", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("book_id", "day", name="uq_activity_book_day"),
    )


def downgrade() -> None:
    op.drop_table("activity_days")
    op.drop_table("translations")
