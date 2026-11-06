"""chapter and verse structure (scriptures)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("books", sa.Column("verse_mode", sa.String(10), nullable=False, server_default="auto"))
    op.add_column("books", sa.Column("verse_summary", JSONB(), nullable=True))
    op.add_column("chapters", sa.Column("section", sa.String(200), nullable=True))
    op.add_column("chapters", sa.Column("number", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("verse_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("verse_end", sa.Integer(), nullable=True))
    op.create_table(
        "verses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False, server_default="verse"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_verses_chapter_position", "verses", ["chapter_id", "position"])


def downgrade() -> None:
    op.drop_table("verses")
    op.drop_column("chunks", "verse_end")
    op.drop_column("chunks", "verse_start")
    op.drop_column("chapters", "number")
    op.drop_column("chapters", "section")
    op.drop_column("books", "verse_summary")
    op.drop_column("books", "verse_mode")
