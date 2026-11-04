"""Create an admin account, or make an existing account an admin and set its password.

    python scripts/create_admin.py                       # uses ADMIN_EMAIL from .env, asks for a password
    python scripts/create_admin.py you@example.com       # that address
"""
from __future__ import annotations

import asyncio
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.passwords import hash_password, password_problem  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


async def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else get_settings().admin_email).strip().lower()
    password = getpass.getpass(f"New password for {email}: ")
    if problem := password_problem(password, email):
        print(f"Password not accepted: {problem}")
        return 1
    if getpass.getpass("Repeat it: ") != password:
        print("The passwords don't match.")
        return 1
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name="Admin", settings={})
            db.add(user)
        user.password_hash = hash_password(password)
        user.is_admin, user.is_active = True, True
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        user.failed_logins, user.locked_until = 0, None
        await db.commit()
    print(f"Done. {email} is an admin and can sign in with that password.")
    return 0


if __name__ == "__main__":
    loop = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    sys.exit(asyncio.run(main(), loop_factory=loop) if loop else asyncio.run(main()))
