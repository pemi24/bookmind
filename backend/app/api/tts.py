"""Text-to-speech: the voices on offer, turning text into sentences, and speaking them.

The app asks for a reply's or a page's sentences, then for each sentence's audio, a few ahead of
what's playing: playback starts after the first sentence instead of the whole text. Browser
voices never come here; they're played by the browser itself.
"""
from __future__ import annotations

from bisect import bisect_right
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.books import listening_dict
from app.auth import ratelimit, scope
from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
from app.db.models import Chapter
from app.db.session import get_db
from app.tts import get_registry
from app.tts.base import TTSError
from app.tts.text import clean_for_speech, split_sentences

router = APIRouter(prefix="/api/tts", tags=["tts"], dependencies=[Depends(current_user)])

_SAMPLES = {
    "en": "Hello! This is how I sound reading your books aloud.",
    "fr": "Bonjour ! Voici comment je lis vos livres à voix haute.",
    "de": "Hallo! So klinge ich, wenn ich Ihre Bücher vorlese.",
    "es": "¡Hola! Así sueno cuando leo tus libros en voz alta.",
    "it": "Ciao! Ecco come suono quando leggo ad alta voce i tuoi libri.",
    "pt": "Olá! É assim que eu soo lendo os seus livros em voz alta.",
}


def _limit(user) -> None:
    ratelimit.check(f"tts:{user.id}", get_settings().tts_rate_limit, 60, "listening requests")


def _no_voice(e: TTSError) -> JSONResponse:
    # 503 + fallback: the app switches to the browser's voices and shows this message.
    return JSONResponse({"detail": f"{e} Using this device's voices instead.", "fallback": "browser"}, 503)


def _audio(spoken) -> Response:
    headers = {"X-TTS-Voice": quote(spoken.voice), "Cache-Control": "private, max-age=86400"}
    if spoken.note:
        headers["X-TTS-Note"] = quote(spoken.note)  # headers are latin-1; the app decodes it
    return Response(spoken.audio.data, media_type=spoken.audio.mime, headers=headers)


@router.get("/voices")
async def voices():
    registry = get_registry()
    return {
        "providers": await registry.catalog(),
        "default_voice": await registry.default_voice(),
        "max_chars": get_settings().tts_max_chars,
    }


class PrepareRequest(BaseModel):
    text: str = Field(max_length=200_000)
    markdown: bool = True  # an AI reply: strip markdown, citation markers, URLs and emoji first


@router.post("/sentences")
async def sentences(req: PrepareRequest):
    """The text as speakable sentences, in reading order."""
    text = clean_for_speech(req.text) if req.markdown else req.text
    return {"sentences": [s.text for s in split_sentences(text)]}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str = Field(max_length=200)
    speed: float = Field(1.0, ge=0.25, le=4.0)
    volume: float = Field(1.0, ge=0.0, le=2.0)


@router.post("/speak")
async def speak(user: CurrentUser, req: SpeakRequest):
    limit = get_settings().tts_max_chars
    if len(req.text) > limit:
        raise HTTPException(413, f"Too much text at once ({len(req.text)} characters; the limit is {limit}).")
    _limit(user)
    try:
        return _audio(await get_registry().speak(req.text, req.voice, req.speed, req.volume))
    except TTSError as e:
        return _no_voice(e)


@router.get("/chapters/{chapter_id}/sentences")
async def chapter_sentences(user: CurrentUser, chapter_id: int, db: AsyncSession = Depends(get_db)):
    """A chapter as sentences for reading aloud. Offsets point into the chapter's text (the reader
    highlights with them); `p` is the start of the sentence's paragraph (text split on blank lines)."""
    ch = await scope.chapter(db, chapter_id, user)  # 404 for someone else's book
    text = ch.text or ""
    paragraphs, at = [], 0
    for para in text.split("\n\n"):
        paragraphs.append(at)
        at += len(para) + 2
    out = []
    for s in split_sentences(text):
        out.append({"start": s.start, "end": s.end, "text": s.text, "p": paragraphs[bisect_right(paragraphs, s.start) - 1]})
    return {"chapter_id": ch.id, "position": ch.position, "title": ch.title, "sentences": out}


class ListeningUpdate(BaseModel):
    position: int = Field(ge=1)  # chapter position (survives re-indexing; chapter ids don't)
    offset: int = Field(default=0, ge=0)  # char offset of the sentence being read


@router.put("/books/{book_id}/listening")
async def save_listening(user: CurrentUser, book_id: int, req: ListeningUpdate, db: AsyncSession = Depends(get_db)):
    """Remember where read-aloud is, for "Continue listening"."""
    book = await scope.book(db, book_id, user)
    exists = await db.scalar(select(Chapter.id).where(Chapter.book_id == book.id, Chapter.position == req.position))
    if exists is None:
        raise HTTPException(400, "This book has no such chapter.")
    book.listen_position, book.listen_offset, book.listen_updated_at = req.position, req.offset, func.now()
    await db.commit()
    await db.refresh(book)
    return listening_dict(book)


@router.delete("/books/{book_id}/listening", status_code=204)
async def clear_listening(user: CurrentUser, book_id: int, db: AsyncSession = Depends(get_db)):
    book = await scope.book(db, book_id, user)
    book.listen_position = book.listen_offset = book.listen_updated_at = None
    await db.commit()


@router.get("/preview")
async def preview(user: CurrentUser, voice: str = Query(max_length=200), speed: float = Query(1.0, ge=0.25, le=4.0)):
    """A short sample of a voice, in its own language."""
    _limit(user)
    registry = get_registry()
    found = await registry.find(voice)
    lang = (found[1].language if found and found[1] else "en")[:2].lower()
    try:
        return _audio(await registry.speak(_SAMPLES.get(lang, _SAMPLES["en"]), voice, speed))
    except TTSError as e:
        return _no_voice(e)
