"""The interface every text-to-speech provider implements."""
from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass, field


class TTSError(Exception):
    """A voice couldn't speak: not installed, unknown, out of quota, network down..."""


@dataclass
class Voice:
    id: str  # "provider:voice", unique across providers
    provider: str
    name: str
    language: str = ""  # BCP 47, e.g. en-US
    accent: str = ""  # e.g. "American", "British (Scottish)"
    gender: str = ""  # female | male | "" (unknown)
    quality: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Audio:
    data: bytes
    mime: str  # audio/wav, audio/mpeg...


@dataclass
class ProviderInfo:
    available: bool
    reason: str = ""  # why it isn't available, in words a user can act on
    voices: list[Voice] = field(default_factory=list)


class TTSProvider(ABC):
    name: str
    label: str
    supports_streaming = False  # audio can start before the whole text is synthesized
    speed_range = (0.5, 2.0)
    supports_pitch = False
    supports_volume = False
    client_side = False  # synthesized in the user's browser, not here

    @abstractmethod
    async def info(self) -> ProviderInfo:
        """Whether it can be used, and its voices."""

    async def list_voices(self) -> list[Voice]:
        return (await self.info()).voices

    @abstractmethod
    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        """Speak `text` with `voice` (the part after "provider:")."""

    async def stream(self, sentences: Iterable[str], voice: str, speed: float = 1.0,
                     volume: float = 1.0) -> AsyncIterator[Audio]:
        """One clip per sentence, each ready as soon as it's synthesized."""
        for s in sentences:
            yield await self.synthesize(s, voice, speed, volume)

    def clamp_speed(self, speed: float) -> float:
        lo, hi = self.speed_range
        return min(hi, max(lo, speed))


def wav_bytes(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw 16-bit PCM in a WAV header (browsers play WAV natively)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
