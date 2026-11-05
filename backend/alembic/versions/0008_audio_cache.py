"""audio cache (synthesized speech saved on disk, per user)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("voice", sa.String(200), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("mime", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        # the file, relative to TTS_CACHE_DIR (the database only says where it is)
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.UniqueConstraint("user_id", "voice", "speed", "text_hash", name="uq_audio_cache_key"),
    )


def downgrade() -> None:
    op.drop_table("audio_cache")
