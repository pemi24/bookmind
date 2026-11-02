"""feature columns: spoiler-aware summaries, per-chapter entity details

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("summaries", sa.Column("up_to_chapter", sa.Integer(), nullable=True))
    op.create_index("ix_summaries_lookup", "summaries", ["book_id", "chapter_id", "length", "up_to_chapter"])
    op.add_column(
        "entities",
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_feature_jobs_book_kind", "feature_jobs", ["book_id", "kind"])
    op.create_index("ix_timeline_book_position", "timeline_events", ["book_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_timeline_book_position", table_name="timeline_events")
    op.drop_index("ix_feature_jobs_book_kind", table_name="feature_jobs")
    op.drop_column("entities", "details")
    op.drop_index("ix_summaries_lookup", table_name="summaries")
    op.drop_column("summaries", "up_to_chapter")
