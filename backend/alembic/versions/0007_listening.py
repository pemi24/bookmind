"""listening position (where read-aloud stopped in each book)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Kept apart from the reading position: listening and reading can be in different places.
    op.add_column("books", sa.Column("listen_position", sa.Integer(), nullable=True))  # chapter position
    op.add_column("books", sa.Column("listen_offset", sa.Integer(), nullable=True))  # char offset of the sentence
    op.add_column("books", sa.Column("listen_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "listen_updated_at")
    op.drop_column("books", "listen_offset")
    op.drop_column("books", "listen_position")
