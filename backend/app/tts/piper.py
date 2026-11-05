"""Piper: free, offline neural voices that run on this computer (pip install piper-tts).

Voices are .onnx files in PIPER_VOICES_DIR (scripts/download_voices.py fetches them). Each voice
loads on first use and stays in memory. Synthesis runs on a small pool of background threads
(ONNX Runtime releases the GIL), so the API keeps answering while a voice is speaking.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import Settings
from app.tts.base import Audio, ProviderInfo, TTSError, TTSProvider, Voice
from app.tts.encode import pcm_audio

# Voice configs don't say who is speaking; these are the common English and French voices.
_GENDER = {
    "lessac": "female", "amy": "female", "kristin": "female", "kathleen": "female", "ljspeech": "female",
    "hfc_female": "female", "alba": "female", "cori": "female", "jenny_dioco": "female",
    "southern_english_female": "female", "siwis": "female",
    "ryan": "male", "joe": "male", "john": "male", "kusal": "male", "norman": "male", "bryce": "male",
    "danny": "male", "hfc_male": "male", "alan": "male", "northern_english_male": "male",
    "southern_english_male": "male", "tom": "male", "gilles": "male",
}
_ACCENT = {
    "en_US": "American", "en_GB": "British", "fr_FR": "French", "de_DE": "German", "es_ES": "Spanish",
    "es_MX": "Mexican", "it_IT": "Italian", "pt_BR": "Brazilian",
}
_ACCENT_DETAIL = {"alba": "Scottish", "northern_english_male": "Northern English", "jenny_dioco": "Irish",
                  "southern_english_female": "Southern English", "southern_english_male": "Southern English"}


def piper_installed() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


class PiperProvider(TTSProvider):
    name = "piper"
    label = "Piper (on this computer)"
    supports_streaming = True  # one clip per sentence
    speed_range = (0.5, 2.0)
    supports_volume = True

    def __init__(self, settings: Settings) -> None:
        self.dir = Path(settings.piper_voices_dir)
        self.wanted = [v.strip() for v in settings.piper_voices.split(",") if v.strip()]
        self.max_loaded = max(1, settings.piper_max_loaded)
        self.format, self.bitrate = settings.tts_audio_format, settings.tts_mp3_bitrate
        self._pool = ThreadPoolExecutor(max_workers=max(1, settings.piper_workers), thread_name_prefix="piper")
        self._loaded: OrderedDict[str, object] = OrderedDict()  # least recently used first
        self._lock = threading.Lock()  # guards _loaded and _loading
        self._loading: dict[str, threading.Lock] = {}  # one per voice: loading one never blocks another

    def _files(self) -> dict[str, Path]:
        found = {p.name.removesuffix(".onnx"): p for p in sorted(self.dir.glob("*.onnx"))
                 if p.with_name(p.name + ".json").exists()}
        return {v: found[v] for v in self.wanted if v in found} if self.wanted else found

    async def info(self) -> ProviderInfo:
        if not piper_installed():
            return ProviderInfo(False, "Piper isn't installed. Run: pip install piper-tts")
        files = self._files()
        if not files:
            missing = ", ".join(self.wanted) or "any voice"
            return ProviderInfo(False, f"No Piper voices downloaded ({missing}). Run: python scripts/download_voices.py")
        return ProviderInfo(True, voices=[self._voice(key, path) for key, path in files.items()])

    def _voice(self, key: str, path: Path) -> Voice:
        try:
            config = json.loads(path.with_name(path.name + ".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
        code = (config.get("language") or {}).get("code") or key.split("-")[0]
        speaker = key.split("-")[1] if key.count("-") >= 2 else key
        accent = _ACCENT.get(code, (config.get("language") or {}).get("country_english", ""))
        if speaker in _ACCENT_DETAIL:
            accent = f"{accent} ({_ACCENT_DETAIL[speaker]})"
        return Voice(
            # "northern_english_male" → "Northern English" (the gender has its own field)
            id=f"piper:{key}", provider=self.name,
            name=re.sub(r"_(?:fe)?male$", "", speaker).replace("_", " ").title(),
            language=code.replace("_", "-"), accent=accent, gender=_GENDER.get(speaker, ""),
            quality=key.rsplit("-", 1)[-1],
        )

    def is_loaded(self, key: str) -> bool:
        return key in self._loaded

    def _load(self, key: str):
        with self._lock:
            if key in self._loaded:
                self._loaded.move_to_end(key)
                return self._loaded[key]
            gate = self._loading.setdefault(key, threading.Lock())
        with gate:  # a second request for the same voice waits for the first load
            with self._lock:
                if key in self._loaded:
                    return self._loaded[key]
            path = self._files().get(key)
            if path is None:
                raise TTSError(f"The Piper voice '{key}' isn't downloaded.")
            from piper import PiperVoice

            voice = PiperVoice.load(path)  # slow (seconds): outside the shared lock
            with self._lock:
                self._loaded[key] = voice
                while len(self._loaded) > self.max_loaded:
                    self._loaded.popitem(last=False)
            return voice

    async def warm(self, key: str) -> None:
        """Load a voice in the background so its first sentence starts quickly."""
        await asyncio.get_running_loop().run_in_executor(self._pool, self._load, key)

    def _run(self, text: str, key: str, speed: float, volume: float) -> Audio:
        from piper import SynthesisConfig

        voice = self._load(key)
        config = SynthesisConfig(length_scale=1.0 / speed, volume=volume)
        rate, pcm = 22050, bytearray()
        for chunk in voice.synthesize(text, syn_config=config):
            rate = chunk.sample_rate
            pcm += chunk.audio_int16_bytes
        return pcm_audio(bytes(pcm), rate, self.format, self.bitrate)  # encoded here, on the pool thread

    async def synthesize(self, text: str, voice: str, speed: float = 1.0, volume: float = 1.0) -> Audio:
        if not piper_installed():
            raise TTSError("Piper isn't installed.")
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._pool, self._run, text, voice, self.clamp_speed(speed),
                                              min(2.0, max(0.0, volume)))
        except TTSError:
            raise
        except Exception as e:  # noqa: BLE001 - a broken model file, out of memory...
            raise TTSError(f"Piper couldn't speak with '{voice}': {e}") from e
