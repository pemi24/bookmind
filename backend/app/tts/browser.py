"""The voices of the user's own browser and operating system (Web Speech API).

They're listed and played entirely in the browser, so this provider has no voices or audio of its
own here. It's always available: when every other voice fails, the app falls back to it.
"""
from __future__ import annotations

from app.tts.base import Audio, ProviderInfo, TTSError, TTSProvider


class BrowserProvider(TTSProvider):
    name = "browser"
    label = "Browser voices (this device)"
    client_side = True
    supports_streaming = True
    speed_range = (0.5, 2.0)
    supports_pitch = True
    supports_volume = True

    async def info(self) -> ProviderInfo:
        return ProviderInfo(True)

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        raise TTSError("Browser voices are played by the browser itself.")
