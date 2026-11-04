"""Text-to-speech: the voices on offer, turning text into sentences, and speaking them.

The app asks for a reply's or a page's sentences, then for each sentence's audio, a few ahead of
what's playing: playback starts after the first sentence instead of the whole text. Browser
voices never come here; they're played by the browser itself.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import ratelimit
from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
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
