"""Every owned row must have an owner.

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OWNED_TABLES = ("books", "conversations", "notes", "quizzes", "flashcards", "entities", "timeline_events")


def upgrade() -> None:
    # Rows created between 0005 and now without an owner: take the book's owner (books themselves
    # fall back to the legacy admin, who owned everything before accounts existed).
    op.execute("UPDATE books SET user_id = (SELECT min(id) FROM users WHERE is_admin) WHERE user_id IS NULL")
    for table in OWNED_TABLES[1:]:
        op.execute(f"UPDATE {table} t SET user_id = b.user_id FROM books b WHERE t.book_id = b.id AND t.user_id IS NULL")
    for table in OWNED_TABLES:
        op.alter_column(table, "user_id", nullable=False)


def downgrade() -> None:
    for table in OWNED_TABLES:
        op.alter_column(table, "user_id", nullable=True)
