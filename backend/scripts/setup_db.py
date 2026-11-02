"""One-command database setup.

    python scripts/setup_db.py            # create DB, enable pgvector, run migrations
    python scripts/setup_db.py --check    # only verify connection + CREATE EXTENSION vector

Reads DATABASE_URL from backend/.env. Uses only psycopg (no app imports) so it
works even when the app itself can't start.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover
    sys.exit("psycopg is not installed. Run: pip install -r requirements.txt")

try:
    from dotenv import load_dotenv

    # Same precedence as app/config.py: .env wins unless BOOKMIND_ENV_OVERRIDE=1 (tests).
    load_dotenv(BACKEND_DIR / ".env", override=os.environ.get("BOOKMIND_ENV_OVERRIDE") != "1")
except ImportError:  # pragma: no cover
    pass


def fail(msg: str, hint: str = "") -> None:
    print(f"\n[ERROR] {msg}")
    if hint:
        print(f"  -> {hint}")
    print("  See README.md > Troubleshooting.")
    sys.exit(1)


def parse_url(url: str) -> dict:
    # Accept SQLAlchemy-style URLs (postgresql+psycopg://...)
    u = urlparse(url.replace("+psycopg", "").replace("+asyncpg", ""))
    if u.scheme not in ("postgresql", "postgres"):
        fail(f"DATABASE_URL must start with postgresql://, got '{u.scheme}://'")
    return {
        "host": u.hostname or "localhost",
        "port": u.port or 5432,
        "user": unquote(u.username or "postgres"),
        "password": unquote(u.password or ""),
        "dbname": (u.path or "/bookmind").lstrip("/") or "bookmind",
    }


def connect(params: dict, dbname: str):
    try:
        return psycopg.connect(
            host=params["host"], port=params["port"], user=params["user"],
            password=params["password"], dbname=dbname, connect_timeout=5, autocommit=True,
        )
    except psycopg.OperationalError as e:
        text = str(e)
        if "password authentication failed" in text or "no password supplied" in text:
            fail("PostgreSQL rejected the username/password.",
                 "Check DATABASE_URL in backend/.env. URL-encode special characters in the password (@ -> %40).")
        if "Connection refused" in text or "could not connect" in text or "timeout" in text.lower():
            fail(f"Cannot reach PostgreSQL at {params['host']}:{params['port']}.",
                 "Is the PostgreSQL service running? Windows: services.msc -> postgresql-x64-NN. "
                 "macOS: brew services start postgresql@17. Linux: sudo systemctl start postgresql")
        fail(f"Could not connect: {text.strip()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only verify connection and pgvector")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        fail("DATABASE_URL is not set.", "Copy backend/.env.example to backend/.env and fill it in.")
    p = parse_url(url)
    print(f"Connecting to {p['host']}:{p['port']} as '{p['user']}' ...")

    with connect(p, "postgres") as conn:
        print("  ", conn.execute("select version()").fetchone()[0])
        exists = conn.execute("select 1 from pg_database where datname = %s", (p["dbname"],)).fetchone()
        if exists:
            print(f"Database '{p['dbname']}' already exists.")
        else:
            try:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(p["dbname"])))
                print(f"Created database '{p['dbname']}'.")
            except psycopg.errors.InsufficientPrivilege:
                fail(f"User '{p['user']}' may not create databases.",
                     f"Run as postgres: CREATE DATABASE {p['dbname']} OWNER {p['user']};")

    with connect(p, p["dbname"]) as conn:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except psycopg.errors.FeatureNotSupported as e:
            fail(f"pgvector is not installed for this PostgreSQL server ({e}).",
                 "Install pgvector (see README.md > Install pgvector) and make sure it targets THIS server's version.")
        except psycopg.errors.UndefinedFile as e:
            fail(f"pgvector files are missing or incomplete: {e}",
                 "Re-run 'nmake /F Makefile.win install' as Administrator (Windows) or reinstall pgvector.")
        except psycopg.errors.InsufficientPrivilege:
            fail("Only a superuser can run CREATE EXTENSION vector the first time.",
                 f"Run once as postgres: psql -U postgres -d {p['dbname']} -c \"CREATE EXTENSION vector;\"")
        ver = conn.execute("select extversion from pg_extension where extname='vector'").fetchone()[0]
        dist = conn.execute("select '[1,2,3]'::vector <=> '[1,2,4]'::vector").fetchone()[0]
        print(f"pgvector {ver} OK (test cosine distance = {dist:.4f}).")

    if args.check:
        print("\nCheck passed.")
        return

    print("Running migrations (alembic upgrade head) ...")
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR)
    if r.returncode != 0:
        fail("Alembic migration failed (see output above).")
    print("\nDatabase is ready.")


if __name__ == "__main__":
    main()
