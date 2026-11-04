"""user accounts: users, sessions, one-time tokens; an owner on every user's data

Existing books, chats, notes... get a "legacy" owner: the admin account from ADMIN_EMAIL /
ADMIN_PASSWORD (.env). Without ADMIN_PASSWORD the account has no password yet; set one with
`python scripts/create_admin.py`.

Child tables (conversations, notes, quizzes, flashcards, entities, timeline_events) get their
owner from their book through a trigger, which also refuses a row whose owner differs from its
book's owner: data can never be linked across users, whatever the application code does.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

CHILD_TABLES = ("conversations", "notes", "quizzes", "flashcards", "entities", "timeline_events")
OWNED_TABLES = ("books", *CHILD_TABLES)


def _legacy_admin() -> tuple[str, str | None]:
    from app.config import get_settings

    s = get_settings()
    email = (s.admin_email or "admin@localhost").strip().lower()
    password_hash = None
    if s.admin_password:
        from argon2 import PasswordHasher

        password_hash = PasswordHasher().hash(s.admin_password)
    return email, password_hash


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("remember", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # The legacy owner / first admin.
    email, password_hash = _legacy_admin()
    conn = op.get_bind()
    admin_id = conn.execute(sa.text(
        "INSERT INTO users (email, display_name, password_hash, is_admin, email_verified_at) "
        "VALUES (:email, 'Admin', :ph, true, now()) RETURNING id"), {"email": email, "ph": password_hash}).scalar()

    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                                       nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        conn.execute(sa.text(f"UPDATE {table} SET user_id = :uid"), {"uid": admin_id})  # noqa: S608 - fixed names

    op.execute("""
        CREATE OR REPLACE FUNCTION bookmind_set_owner() RETURNS trigger AS $$
        DECLARE owner integer;
        BEGIN
            SELECT user_id INTO owner FROM books WHERE id = NEW.book_id;
            IF NEW.user_id IS NULL THEN
                NEW.user_id := owner;
            ELSIF owner IS NOT NULL AND NEW.user_id <> owner THEN
                RAISE EXCEPTION 'bookmind: % row belongs to user % but its book % belongs to user %',
                    TG_TABLE_NAME, NEW.user_id, NEW.book_id, owner;
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    for table in CHILD_TABLES:
        op.execute(f"CREATE TRIGGER {table}_owner BEFORE INSERT OR UPDATE OF book_id, user_id ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION bookmind_set_owner()")


def downgrade() -> None:
    for table in CHILD_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_owner ON {table}")
    op.execute("DROP FUNCTION IF EXISTS bookmind_set_owner()")
    for table in OWNED_TABLES:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
    op.drop_table("auth_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
