"""reader highlights (colour + comment) and server-side reading progress

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("color", sa.String(20), nullable=True))
    op.add_column("notes", sa.Column("comment", sa.Text(), nullable=True))
    # Chapter *positions*, not ids: chapter rows are recreated on re-index, positions survive.
    op.add_column("books", sa.Column("reading_position", sa.Integer(), nullable=True))
    op.add_column("books", sa.Column("reading_offset", sa.Integer(), nullable=True))
    op.add_column("books", sa.Column("furthest_position", sa.Integer(), nullable=True))
    op.add_column("books", sa.Column("reading_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "reading_updated_at")
    op.drop_column("books", "furthest_position")
    op.drop_column("books", "reading_offset")
    op.drop_column("books", "reading_position")
    op.drop_column("notes", "comment")
    op.drop_column("notes", "color")
