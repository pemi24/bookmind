"""Optional cloud voices: OpenAI, ElevenLabs and Google (Gemini). Each one is offered only when its
API key is in backend/.env (Google also needs TTS_GOOGLE_ENABLED=true)."""
from __future__ import annotations

import asyncio
import base64
import re

import httpx

from app.config import Settings
from app.tts.base import Audio, ProviderInfo, TTSError, TTSProvider, Voice
from app.tts.encode import pcm_audio

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _http_error(provider: str, e: Exception) -> TTSError:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        why = {401: "the API key was refused", 403: "the API key was refused", 429: "out of quota or rate-limited"}
        return TTSError(f"{provider} voices: {why.get(code, f'error {code}')}.")
    if isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
        return TTSError(f"{provider} voices: couldn't reach the service (no internet?).")
    return TTSError(f"{provider} voices: {e}")


class _Cloud(TTSProvider):
    supports_streaming = True
    supports_volume = False

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(timeout=_TIMEOUT, transport=transport)

    async def _post(self, url: str, **kw) -> httpx.Response:
        try:
            r = await self._client.post(url, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            raise _http_error(self.label, e) from e


# Built-in voices of OpenAI's speech models (they speak any language).
_OPENAI_VOICES = [
    ("alloy", ""), ("ash", "male"), ("ballad", "male"), ("coral", "female"), ("echo", "male"),
    ("fable", "male"), ("nova", "female"), ("onyx", "male"), ("sage", "female"), ("shimmer", "female"),
    ("verse", "male"),
]


class OpenAIProvider(_Cloud):
    name = "openai"
    label = "OpenAI"
    speed_range = (0.25, 4.0)

    async def info(self) -> ProviderInfo:
        voices = [Voice(f"openai:{v}", self.name, v.title(), "", "Multilingual", g) for v, g in _OPENAI_VOICES]
        return ProviderInfo(True, voices=voices)

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        r = await self._post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={"model": self.settings.openai_tts_model, "voice": voice, "input": text,
                  "speed": self.clamp_speed(speed), "response_format": "mp3"},
        )
        return Audio(r.content, "audio/mpeg")


class ElevenLabsProvider(_Cloud):
    name = "elevenlabs"
    label = "ElevenLabs"
    speed_range = (0.7, 1.2)  # the most its voices allow

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(settings, transport)
        self._voices: list[Voice] | None = None

    async def info(self) -> ProviderInfo:
        if self._voices is None:
            try:
                r = await self._client.get("https://api.elevenlabs.io/v1/voices",
                                           headers={"xi-api-key": self.settings.elevenlabs_api_key})
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                return ProviderInfo(False, str(_http_error(self.label, e)))
            self._voices = [
                Voice(f"elevenlabs:{v['voice_id']}", self.name, v.get("name", "Voice"),
                      "", (v.get("labels") or {}).get("accent", "").title(),
                      (v.get("labels") or {}).get("gender", "").lower())
                for v in r.json().get("voices", [])
            ]
        return ProviderInfo(True, voices=self._voices)

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        r = await self._post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            headers={"xi-api-key": self.settings.elevenlabs_api_key},
            json={"text": text, "model_id": self.settings.elevenlabs_model,
                  "voice_settings": {"speed": self.clamp_speed(speed)}},
        )
        return Audio(r.content, "audio/mpeg")


# Gemini's prebuilt voices (they speak many languages); the genders are Google's own descriptions.
_GOOGLE_VOICES = [
    ("Kore", "female"), ("Aoede", "female"), ("Leda", "female"), ("Zephyr", "female"),
    ("Puck", "male"), ("Charon", "male"), ("Fenrir", "male"), ("Orus", "male"),
]


class GoogleProvider(_Cloud):
    name = "google"
    label = "Google (Gemini)"
    speed_range = (1.0, 1.0)  # no speed setting; the browser's playback rate does it instead

    async def info(self) -> ProviderInfo:
        voices = [Voice(f"google:{v}", self.name, v, "", "Multilingual", g) for v, g in _GOOGLE_VOICES]
        return ProviderInfo(True, voices=voices)

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        model = self.settings.google_tts_model
        r = await self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
                },
            },
        )
        try:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError, ValueError) as e:
            raise TTSError("Google voices: the reply had no audio.") from e
        rate = re.search(r"rate=(\d+)", part.get("mimeType", ""))
        pcm, rate = base64.b64decode(part["data"]), int(rate.group(1)) if rate else 24000
        s = self.settings
        return await asyncio.to_thread(pcm_audio, pcm, rate, s.tts_audio_format, s.tts_mp3_bitrate)
