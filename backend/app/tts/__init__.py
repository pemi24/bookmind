"""Text-to-speech: a registry of voice providers, selected in backend/.env (TTS_PROVIDERS).

Voice ids are "provider:voice" (e.g. "piper:en_US-lessac-medium"). speak() never gives up on a
missing or failing voice without trying the server's default voice first, and says so; when no
voice on this server can speak, the app falls back to the browser's own voices.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings
from app.tts.base import Audio, TTSError, TTSProvider, Voice

log = logging.getLogger("bookmind.tts")

KNOWN = ("piper", "browser", "openai", "elevenlabs", "google")
BROWSER = "browser:"  # the browser's own default voice


def _create(name: str, settings: Settings) -> TTSProvider | None:
    """The provider, or None when it isn't set up (a cloud provider without its key)."""
    if name == "piper":
        from app.tts.piper import PiperProvider

        return PiperProvider(settings)
    if name == "browser":
        from app.tts.browser import BrowserProvider

        return BrowserProvider()
    if name == "openai" and settings.openai_api_key:
        from app.tts.cloud import OpenAIProvider

        return OpenAIProvider(settings)
    if name == "elevenlabs" and settings.elevenlabs_api_key:
        from app.tts.cloud import ElevenLabsProvider

        return ElevenLabsProvider(settings)
    if name == "google" and settings.tts_google_enabled and settings.gemini_api_key:
        from app.tts.cloud import GoogleProvider

        return GoogleProvider(settings)
    return None


class Registry:
    def __init__(self, settings: Settings, providers: list[TTSProvider] | None = None) -> None:
        self.settings = settings
        if providers is None:
            names = [n.strip().lower() for n in settings.tts_providers.split(",") if n.strip()]
            unknown = [n for n in names if n not in KNOWN]
            if unknown:
                log.warning("TTS_PROVIDERS: unknown provider(s) %s (known: %s)", unknown, ", ".join(KNOWN))
            providers = [p for n in dict.fromkeys(names + ["browser"]) if n in KNOWN and (p := _create(n, settings))]
        self.providers: dict[str, TTSProvider] = {p.name: p for p in providers}

    async def catalog(self) -> list[dict]:
        """Every enabled provider with its voices, or why it can't be used right now."""
        infos = await asyncio.gather(*(p.info() for p in self.providers.values()))
        return [
            {
                "id": p.name, "label": p.label, "available": i.available, "reason": i.reason,
                "client_side": p.client_side, "supports_streaming": p.supports_streaming,
                "speed_range": list(p.speed_range), "pitch": p.supports_pitch, "volume": p.supports_volume,
                "voices": [v.to_dict() for v in i.voices],
            }
            for p, i in zip(self.providers.values(), infos)
        ]

    async def find(self, voice_id: str) -> tuple[TTSProvider, Voice | None] | None:
        """The provider for a voice id and the voice itself, if both exist and work now."""
        provider_name, _, key = (voice_id or "").partition(":")
        p = self.providers.get(provider_name)
        if p is None:
            return None
        if p.client_side:
            return p, None
        info = await p.info()
        voice = next((v for v in info.voices if v.id == voice_id), None) if info.available else None
        return (p, voice) if voice else None

    async def default_voice(self) -> str:
        configured = self.settings.tts_default_voice.strip()
        if configured and await self.find(configured):
            return configured
        piper = self.providers.get("piper")
        if piper:
            info = await piper.info()
            if info.available and info.voices:
                return info.voices[0].id
        return BROWSER

    async def speak(self, text: str, voice_id: str, speed: float = 1.0, volume: float = 1.0) -> "Spoken":
        """Audio for `text`. A missing or failing voice falls back to the server default (with a
        note saying so). TTSError when nothing here can speak: the browser's voices take over."""
        note = None
        found = await self.find(voice_id)
        if found is None or found[0].client_side:
            fallback = await self.default_voice()
            if fallback == BROWSER:
                raise TTSError(f"The voice '{voice_id}' isn't available, and this server has no other voices.")
            if found is None:
                note = f"The voice '{voice_id}' isn't available any more, so another voice is reading."
            voice_id, found = fallback, await self.find(fallback)
        provider = found[0]
        key = voice_id.partition(":")[2]
        try:
            return Spoken(await provider.synthesize(text, key, speed, volume), voice_id, note)
        except TTSError as e:
            fallback = await self.default_voice()
            if fallback in (voice_id, BROWSER):
                raise
            log.warning("TTS %s failed (%s); falling back to %s", voice_id, e, fallback)
            p2 = (await self.find(fallback))[0]
            audio = await p2.synthesize(text, fallback.partition(":")[2], speed, volume)
            return Spoken(audio, fallback, f"{e} Another voice is reading instead.")

    async def warm_default(self) -> None:
        """Load the default Piper voice in the background (it takes several seconds)."""
        voice = await self.default_voice()
        piper = self.providers.get("piper")
        if piper and voice.startswith("piper:"):
            try:
                await piper.warm(voice.partition(":")[2])  # type: ignore[attr-defined]
                log.info("TTS voice ready: %s", voice)
            except Exception as e:  # noqa: BLE001 - only a head start; speaking reports real errors
                log.warning("Couldn't preload the voice %s: %s", voice, e)


@dataclass
class Spoken:
    audio: Audio
    voice: str  # the voice that actually spoke
    note: str | None  # set when it isn't the one asked for, and why


@lru_cache
def get_registry() -> Registry:
    return Registry(get_settings())
