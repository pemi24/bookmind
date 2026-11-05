"""Your account: profile, email, password, preferences, signed-in devices, export, delete."""
from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import EMAIL, _norm, _send_verification, user_dict
from app.api.books import user_upload_dir
from app.auth import mailer, ratelimit, sessions
from app.auth.deps import CurrentUser, current_session, current_user
from app.auth.passwords import hash_password, password_problem, verify_password
from app.config import get_settings
from app.db.models import (
    Book, Chapter, Conversation, Flashcard, Message, Note, Quiz, User, UserSession,
)
from app.db.session import get_db
from app.llm.providers import PROVIDERS, create_provider
from app.tts import KNOWN as TTS_PROVIDERS
from app.tts import cache as audio_cache

router = APIRouter(prefix="/api/account", tags=["account"], dependencies=[Depends(current_user)])
HOUR = 60 * 60


async def _check_password(user: User, password: str) -> None:
    """Re-asks for the password before sensitive changes (rate-limited like sign-in)."""
    ratelimit.check(f"reauth:{user.id}", 10, 15 * 60, "password attempts")
    if not verify_password(user.password_hash, password):
        raise HTTPException(403, "That password isn't right.")


# ---------------------------------------------------------------- profile and preferences

class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


@router.patch("/profile")
async def update_profile(user: CurrentUser, req: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    name = " ".join(req.display_name.split())
    if not name:
        raise HTTPException(422, "Your name can't be empty.")
    user.display_name = name
    await db.commit()
    return {"user": user_dict(user)}


class PreferencesUpdate(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    llm_provider: str | None = Field(default=None, max_length=30)  # "" = the server's default
    llm_model: str | None = Field(default=None, max_length=120)  # "" = the provider's default
    # Listening: "provider:voice" ids ("" = the server's default voice), one for chat replies and
    # one for reading books. Browser voice ids are only known to the browser, so they aren't checked
    # against the server's list; a voice that has gone away falls back when it's used.
    tts_chat_voice: str | None = Field(default=None, max_length=200)
    tts_read_voice: str | None = Field(default=None, max_length=200)
    tts_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    tts_pitch: float | None = Field(default=None, ge=0.5, le=2.0)  # browser voices only
    tts_volume: float | None = Field(default=None, ge=0.0, le=1.0)
    tts_auto_read: bool | None = None  # read each new chat reply aloud


_VOICE_ID = re.compile(r"(?:%s):[^\x00-\x1f]*" % "|".join(TTS_PROVIDERS))


@router.get("/ai-options")
async def ai_options(user: CurrentUser):
    """The AI providers this server has keys for, with their default models."""
    s = get_settings()
    out = []
    for name in PROVIDERS:
        try:
            p = create_provider(name, s.model_copy(update={"llm_provider": name, "llm_model": ""}))
        except Exception:  # noqa: BLE001 - a provider whose package isn't installed
            continue
        if not p.configured():
            continue
        available = True
        if p.local:  # a local model server (Ollama) may simply not be running on this computer
            try:
                available = (await asyncio.wait_for(p.check(), 3)).ok
            except Exception:  # noqa: BLE001
                available = False
            finally:
                await p.aclose()
        out.append({"name": name, "default_model": p.model, "local": p.local, "available": available})
    return {"server_default": {"name": s.llm_provider.strip().lower(), "model": s.llm_model}, "providers": out}


@router.patch("/preferences")
async def update_preferences(user: CurrentUser, req: PreferencesUpdate, db: AsyncSession = Depends(get_db)):
    prefs = dict(user.settings or {})
    if req.theme is not None:
        prefs["theme"] = req.theme
    if req.llm_provider is not None:
        name = req.llm_provider.strip().lower()
        if name and name not in PROVIDERS:
            raise HTTPException(422, f"Unknown AI provider. Options: {', '.join(PROVIDERS)}.")
        if name:
            s = get_settings()
            if not create_provider(name, s.model_copy(update={"llm_provider": name})).configured():
                raise HTTPException(422, f"This server has no API key for {name}. Ask whoever runs BookMind to add one.")
        prefs["llm_provider"] = name
        if not name:
            prefs["llm_model"] = ""
    if req.llm_model is not None:
        model = req.llm_model.strip()
        if model and not re.fullmatch(r"[\w.:/@+-]+", model):
            raise HTTPException(422, "That doesn't look like a model name.")
        prefs["llm_model"] = model if prefs.get("llm_provider") else ""
    for key in ("tts_chat_voice", "tts_read_voice"):
        voice = getattr(req, key)
        if voice is not None:
            voice = voice.strip()
            if voice and not _VOICE_ID.fullmatch(voice):
                raise HTTPException(422, "That isn't a voice BookMind knows.")
            prefs[key] = voice
    for key in ("tts_speed", "tts_pitch", "tts_volume", "tts_auto_read"):
        if (value := getattr(req, key)) is not None:
            prefs[key] = value
    user.settings = prefs
    await db.commit()
    return {"user": user_dict(user)}


# ---------------------------------------------------------------- email and password

class EmailChange(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


@router.post("/email")
async def change_email(user: CurrentUser, req: EmailChange, request: Request, db: AsyncSession = Depends(get_db)):
    await _check_password(user, req.password)
    email = _norm(req.email)
    if not EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if email == user.email:
        return {"user": user_dict(user)}
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Another account already uses that email.")
    old = user.email
    user.email = email
    s = get_settings()
    if s.require_email_verification:
        user.email_verified_at = None
    await db.commit()
    await mailer.send_email(old, "Your BookMind email was changed",
                            f"Hello {user.display_name},\n\nYour BookMind account now uses {email} instead of this "
                            "address. If you didn't do this, reset your password straight away.")
    if s.require_email_verification:
        await _send_verification(db, user, request)
    return {"user": user_dict(user)}


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


@router.post("/password")
async def change_password(req: PasswordChange, found=Depends(current_session), db: AsyncSession = Depends(get_db)):
    sess, user = found
    await _check_password(user, req.current_password)
    if problem := password_problem(req.new_password, user.email):
        raise HTTPException(422, problem)
    user.password_hash = hash_password(req.new_password)
    # Every other device must sign in again with the new password; this one stays signed in.
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != sess.id))
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- signed-in devices

@router.get("/sessions")
async def list_sessions(found=Depends(current_session), db: AsyncSession = Depends(get_db)):
    sess, user = found
    rows = (await db.execute(select(UserSession).where(UserSession.user_id == user.id,
                                                       UserSession.expires_at > func.now())
                             .order_by(UserSession.last_seen_at.desc()))).scalars()
    return [{"id": r.id, "current": r.id == sess.id, "user_agent": r.user_agent, "ip": r.ip,
             "created_at": r.created_at.isoformat(), "last_seen_at": r.last_seen_at.isoformat()} for r in rows]


@router.delete("/sessions/{session_id}", status_code=204)
async def end_session(session_id: int, found=Depends(current_session), db: AsyncSession = Depends(get_db)):
    sess, user = found
    if session_id == sess.id:
        raise HTTPException(400, "Use Sign out to end this session.")
    r = await db.execute(delete(UserSession).where(UserSession.id == session_id, UserSession.user_id == user.id))
    if not r.rowcount:
        raise HTTPException(404, "Not found.")
    await db.commit()


# ---------------------------------------------------------------- export

def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")[:60] or "book"


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _cols(obj, *names: str) -> dict:
    return {n: _iso(getattr(obj, n)) for n in names}


async def _export_data(db: AsyncSession, user: User) -> list[tuple[str, bytes | Path]]:
    """Everything that is yours, as (path in the zip, content or file to copy)."""
    from app.features import notes as notes_export

    files: list[tuple[str, bytes | Path]] = []
    dump = lambda o: json.dumps(o, ensure_ascii=False, indent=2).encode()  # noqa: E731
    files.append(("account.json", dump({**user_dict(user), "exported_at": datetime.now(timezone.utc).isoformat()})))

    books = (await db.execute(select(Book).where(Book.user_id == user.id).order_by(Book.id))).scalars().all()
    chapter_titles = dict((await db.execute(
        select(Chapter.id, Chapter.title).join(Book, Book.id == Chapter.book_id).where(Book.user_id == user.id))).all())
    for b in books:
        base = f"books/{b.id}-{_slug(b.title)}"
        files.append((f"{base}/book.json", dump(_cols(
            b, "id", "title", "author", "filename", "file_type", "status", "created_at", "furthest_position",
            "reading_position", "reading_offset", "reading_updated_at"))))
        if b.file_path and Path(b.file_path).is_file():
            files.append((f"{base}/{b.filename}", Path(b.file_path)))

        notes = (await db.execute(select(Note).where(Note.book_id == b.id, Note.user_id == user.id)
                                  .order_by(Note.id))).scalars().all()
        if notes:
            files.append((f"{base}/notes.md", notes_export.to_markdown(b, notes).encode()))
            files.append((f"{base}/notes.json", dump([_cols(
                n, "id", "kind", "title", "content", "comment", "tags", "color", "location", "created_at")
                for n in notes])))

        convs = (await db.execute(select(Conversation).where(Conversation.book_id == b.id,
                                                             Conversation.user_id == user.id)
                                  .order_by(Conversation.id))).scalars().all()
        if convs:
            out = []
            for c in convs:
                msgs = (await db.execute(select(Message).where(Message.conversation_id == c.id)
                                         .order_by(Message.id))).scalars().all()
                out.append({**_cols(c, "id", "title", "mode", "persona", "book_ids", "created_at", "updated_at"),
                            "messages": [{"role": m.role, "content": m.content, "created_at": _iso(m.created_at),
                                          "sources": [{k: s.get(k) for k in ("marker", "book_title", "chapter_title", "page_start", "text")}
                                                      for s in (m.meta or {}).get("sources", [])]}
                                         for m in msgs]})
            files.append((f"{base}/chats.json", dump(out)))

        quizzes = (await db.execute(select(Quiz).where(Quiz.book_id == b.id, Quiz.user_id == user.id))).scalars().all()
        if quizzes:
            files.append((f"{base}/quizzes.json", dump([_cols(q, "id", "title", "questions", "attempts", "created_at")
                                                        for q in quizzes])))
        cards = (await db.execute(select(Flashcard).where(Flashcard.book_id == b.id,
                                                          Flashcard.user_id == user.id))).scalars().all()
        if cards:
            files.append((f"{base}/flashcards.json", dump([
                {**_cols(c, "id", "front", "back", "interval_days", "due_at", "created_at"),
                 "chapter": chapter_titles.get(c.chapter_id)} for c in cards])))

    files.append(("README.txt", (
        "Your BookMind export\n\n"
        "account.json      your profile and preferences\n"
        "books/<id>-<title>/\n"
        "  book.json       details and reading progress\n"
        "  <file>          the book file you uploaded or downloaded\n"
        "  notes.md/.json  highlights and notes\n"
        "  chats.json      conversations, with the passages each answer used\n"
        "  quizzes.json, flashcards.json\n").encode()))
    return files


def _zip(files: list[tuple[str, bytes | Path]]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            if isinstance(content, Path):
                z.write(content, name)
            else:
                z.writestr(name, content)
    buf.seek(0)
    return buf


@router.get("/export")
async def export_account(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """A zip of everything in your account: books, notes, chats, quizzes, flashcards."""
    ratelimit.check(f"export:{user.id}", 10, HOUR, "exports")
    buf = await asyncio.to_thread(_zip, await _export_data(db, user))
    name = f"bookmind-export-{datetime.now().strftime('%Y-%m-%d')}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- delete

class DeleteAccount(BaseModel):
    password: str = Field(max_length=256)


async def delete_user_and_files(db: AsyncSession, user: User) -> None:
    """Removes the account, everything it owns (database cascade) and its book files."""
    paths = [Path(p) for p in (await db.execute(select(Book.file_path).where(Book.user_id == user.id))).scalars() if p]
    folder = user_upload_dir(user.id)
    user_id = user.id
    await db.delete(user)
    await db.commit()
    for p in paths:
        p.unlink(missing_ok=True)
    shutil.rmtree(folder, ignore_errors=True)
    audio_cache.remove_user(user_id)  # its rows went with the account


@router.post("/delete")
async def delete_account(user: CurrentUser, req: DeleteAccount, response: Response, db: AsyncSession = Depends(get_db)):
    await _check_password(user, req.password)
    if user.is_admin:
        others = await db.scalar(select(func.count()).select_from(User).where(
            User.is_admin, User.is_active, User.id != user.id))
        if not others:
            raise HTTPException(409, "You're the only admin. Make another account an admin before deleting yours.")
    await delete_user_and_files(db, user)
    sessions.clear_cookies(response)
    return {"ok": True}
