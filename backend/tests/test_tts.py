"""Text-to-speech: cleaning and sentence splitting, provider selection and fallback, cloud request
shapes (mocked), and the API's limits. A real Piper run is opt-in (BOOKMIND_TEST_PIPER=1): loading
a voice takes several seconds."""
from __future__ import annotations

import base64
import json
import os
from urllib.parse import unquote

import httpx
import pytest

from app.config import get_settings
from app.tts import BROWSER, Registry
from app.tts.base import Audio, ProviderInfo, TTSError, TTSProvider, Voice
from app.tts.text import clean_for_speech, split_sentences
from tests.conftest import signed_in

# ---------- text ----------


def test_clean_strips_markdown_citations_urls_and_emoji():
    reply = (
        "## Key points\n"
        "- **Courage** matters [1, 2]. See https://example.com/a?b=1 😀\n"
        "- The _fox_ ran[3].\n"
        "```python\nprint('code is not read')\n```\n"
        "> A quote\n"
        "[the link text](http://a.b/c) and snake_case_name stay. 🦊👍🏽"
    )
    spoken = clean_for_speech(reply)
    assert spoken == (
        "Key points. Courage matters. See. The fox ran. A quote. the link text and snake_case_name stay."
    )
    for gone in ("**", "[1", "http", "😀", "🦊", "#", "```", "print"):
        assert gone not in spoken


def test_clean_keeps_ordinary_prose():
    assert clean_for_speech("It cost 3.50 [2–4], she said: yes!") == "It cost 3.50, she said: yes!"


def test_clean_keeps_the_full_stop_after_a_url():
    spoken = clean_for_speech("Spring came 🌸 at last, see https://x.org/Fox_(novel). Then what? (www.y.com)")
    assert spoken == "Spring came at last, see. Then what?"
    assert clean_for_speech("Read it (https://a.b/c) today.") == "Read it today."


def test_sentences_respect_abbreviations_initials_and_quotes():
    text = ('Mr. Smith met Dr. J. R. R. Tolkien at 3.30 p.m. on Monday. "Hello!" he said. '
            "It was... odd. Wasn't it?\n\nA new paragraph without a full stop\n\nLast one.")
    got = split_sentences(text)
    assert [s.text for s in got] == [
        "Mr. Smith met Dr. J. R. R. Tolkien at 3.30 p.m. on Monday.",
        '"Hello!" he said.',
        "It was... odd.",
        "Wasn't it?",
        "A new paragraph without a full stop",
        "Last one.",
    ]
    for s in got:  # offsets point at the original text (the reader highlights with them)
        assert " ".join(text[s.start:s.end].split()) == s.text


def test_sentences_cut_long_runs_and_skip_decorations():
    long = "This goes on, " * 60 + "and ends."
    pieces = split_sentences(long, max_chars=120)
    assert len(pieces) > 1 and all(len(p.text) <= 120 for p in pieces)
    assert " ".join(p.text for p in pieces) == " ".join(long.split())
    assert [s.text for s in split_sentences("One.\n\n* * *\n\nTwo.")] == ["One.", "Two."]
    assert split_sentences("") == [] and split_sentences("   \n ") == []


def test_sentences_keep_line_wraps_inside_a_sentence():
    # PDFs wrap lines with single newlines; only blank lines are paragraph breaks
    text = "The frost came early\nthat year, and the fox\nwaited. Spring followed."
    assert [s.text for s in split_sentences(text)] == [
        "The frost came early that year, and the fox waited.", "Spring followed."]


# ---------- providers and fallback ----------


class Fake(TTSProvider):
    def __init__(self, name, voices=("a", "b"), fail=False, available=True):
        self.name, self.label = name, name.title()
        self._voices, self.fail, self.available, self.calls = voices, fail, available, []

    async def info(self):
        if not self.available:
            return ProviderInfo(False, f"{self.name} is off")
        return ProviderInfo(True, voices=[Voice(f"{self.name}:{v}", self.name, v) for v in self._voices])

    async def synthesize(self, text, voice, speed=1.0, volume=1.0):
        self.calls.append((text, voice, speed))
        if self.fail:
            raise TTSError(f"{self.name} is down.")
        return Audio(f"{self.name}/{voice}/{text}".encode(), "audio/wav")


def _registry(*providers, default=""):
    from app.tts.browser import BrowserProvider

    s = get_settings().model_copy(update={"tts_default_voice": default})
    return Registry(s, [*providers, BrowserProvider()])


@pytest.mark.asyncio
async def test_speaks_with_the_chosen_voice():
    piper, cloud = Fake("piper"), Fake("cloud")
    spoken = await _registry(piper, cloud).speak("Hi.", "cloud:b", 1.25)
    assert (spoken.audio.data, spoken.voice, spoken.note) == (b"cloud/b/Hi.", "cloud:b", None)
    assert cloud.calls == [("Hi.", "b", 1.25)] and piper.calls == []


@pytest.mark.asyncio
async def test_missing_voice_falls_back_to_default_with_a_note():
    piper = Fake("piper")
    spoken = await _registry(piper).speak("Hi.", "piper:deleted-voice")
    assert spoken.voice == "piper:a" and "isn't available" in spoken.note
    # a provider that was switched off (e.g. its API key removed) is treated the same way
    spoken = await _registry(piper).speak("Hi.", "elevenlabs:xyz")
    assert spoken.voice == "piper:a" and spoken.note


@pytest.mark.asyncio
async def test_failing_provider_falls_back_to_default():
    piper, cloud = Fake("piper"), Fake("cloud", fail=True)
    spoken = await _registry(piper, cloud).speak("Hi.", "cloud:a")
    assert spoken.voice == "piper:a" and "cloud is down." in spoken.note


@pytest.mark.asyncio
async def test_default_voice_failing_raises_for_browser_fallback():
    with pytest.raises(TTSError, match="down"):
        await _registry(Fake("piper", fail=True)).speak("Hi.", "piper:a")
    # no server voices at all (Piper not installed, no keys): only the browser can speak
    reg = _registry(Fake("piper", available=False))
    assert await reg.default_voice() == BROWSER
    with pytest.raises(TTSError):
        await reg.speak("Hi.", "piper:a")


@pytest.mark.asyncio
async def test_configured_default_voice_and_catalog():
    reg = _registry(Fake("piper"), Fake("cloud"), default="cloud:b")
    assert await reg.default_voice() == "cloud:b"
    cat = {p["id"]: p for p in await reg.catalog()}
    assert [v["id"] for v in cat["cloud"]["voices"]] == ["cloud:a", "cloud:b"]
    assert cat["browser"]["client_side"] and cat["browser"]["available"]
    # an unknown configured default is ignored
    assert await _registry(Fake("piper"), default="nope:x").default_voice() == "piper:a"


def test_cloud_providers_hidden_without_keys():
    s = get_settings().model_copy(update={
        "tts_providers": "piper,openai,elevenlabs,google,browser", "openai_api_key": "",
        "elevenlabs_api_key": "", "tts_google_enabled": True, "gemini_api_key": ""})
    assert list(Registry(s).providers) == ["piper", "browser"]
    s = s.model_copy(update={"openai_api_key": "sk-test", "gemini_api_key": "g", "tts_google_enabled": False})
    assert list(Registry(s).providers) == ["piper", "openai", "browser"]  # Google needs opting in
    # browser is always there, even when not listed
    assert "browser" in Registry(s.model_copy(update={"tts_providers": "piper"})).providers


@pytest.mark.asyncio
async def test_piper_reports_missing_voices(tmp_path):
    from app.tts.piper import PiperProvider

    p = PiperProvider(get_settings().model_copy(update={"piper_voices_dir": tmp_path, "piper_voices": "en_US-x-medium"}))
    info = await p.info()
    assert not info.available and "download_voices" in info.reason
    with pytest.raises(TTSError, match="isn't downloaded"):
        await p.synthesize("Hi.", "en_US-x-medium")


# ---------- cloud request shapes (no network) ----------


@pytest.mark.asyncio
async def test_openai_request_and_errors():
    from app.tts.cloud import OpenAIProvider

    seen = {}

    def handler(req: httpx.Request):
        seen.update(json.loads(req.content), auth=req.headers["authorization"])
        return httpx.Response(200, content=b"ID3mp3")

    s = get_settings().model_copy(update={"openai_api_key": "sk-test"})
    audio = await OpenAIProvider(s, httpx.MockTransport(handler)).synthesize("Hello.", "nova", 9)
    assert audio == Audio(b"ID3mp3", "audio/mpeg")
    assert seen["voice"] == "nova" and seen["input"] == "Hello." and seen["speed"] == 4.0
    assert seen["auth"] == "Bearer sk-test"
    quota = OpenAIProvider(s, httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(TTSError, match="quota"):
        await quota.synthesize("Hello.", "nova")


@pytest.mark.asyncio
async def test_google_wraps_pcm_in_wav():
    from app.tts.cloud import GoogleProvider

    pcm = b"\x00\x01" * 100
    body = {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    s = get_settings().model_copy(update={"gemini_api_key": "g"})
    audio = await GoogleProvider(s, httpx.MockTransport(lambda r: httpx.Response(200, json=body))).synthesize("Hi.", "Kore")
    assert audio.mime == "audio/wav" and audio.data.startswith(b"RIFF") and audio.data.endswith(pcm)


@pytest.mark.asyncio
async def test_elevenlabs_lists_voices_and_reports_bad_key():
    from app.tts.cloud import ElevenLabsProvider

    s = get_settings().model_copy(update={"elevenlabs_api_key": "e"})
    voices = {"voices": [{"voice_id": "v1", "name": "Rachel", "labels": {"gender": "Female", "accent": "american"}}]}
    ok = ElevenLabsProvider(s, httpx.MockTransport(lambda r: httpx.Response(200, json=voices)))
    [v] = (await ok.info()).voices
    assert (v.id, v.name, v.gender, v.accent) == ("elevenlabs:v1", "Rachel", "female", "American")
    bad = ElevenLabsProvider(s, httpx.MockTransport(lambda r: httpx.Response(401)))
    info = await bad.info()
    assert not info.available and "refused" in info.reason


# ---------- API ----------

pytestmark_api = pytest.mark.asyncio(loop_scope="session")


def _app():
    from app.main import app

    return app


@pytest.fixture
def fake_registry(monkeypatch):
    reg = _registry(Fake("piper"), Fake("cloud", fail=True))
    monkeypatch.setattr("app.api.tts.get_registry", lambda: reg)
    return reg


@pytestmark_api
async def test_api_requires_sign_in(test_db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as c:
        assert (await c.get("/api/tts/voices")).status_code == 401
        r = await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "piper:a"},
                         headers={"X-Requested-With": "BookMind"})
        assert r.status_code == 401


@pytestmark_api
async def test_api_voices_sentences_and_speak(test_db, fake_registry):
    async with signed_in(_app()) as c:
        r = (await c.get("/api/tts/voices")).json()
        assert r["default_voice"] == "piper:a" and r["max_chars"] == get_settings().tts_max_chars
        assert [p["id"] for p in r["providers"]] == ["piper", "cloud", "browser"]

        r = await c.post("/api/tts/sentences", json={"text": "**Yes** [1]. It is. 🦊"})
        assert r.json() == {"sentences": ["Yes.", "It is."]}

        r = await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "piper:b", "speed": 1.5})
        assert r.status_code == 200 and r.content == b"piper/b/Hi." and r.headers["content-type"] == "audio/wav"
        assert r.headers["x-tts-voice"] == "piper%3Ab" and "x-tts-note" not in r.headers

        r = await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "cloud:a"})  # cloud fails
        assert r.content == b"piper/a/Hi." and "down" in unquote(r.headers["x-tts-note"])

        r = await c.get("/api/tts/preview", params={"voice": "piper:b"})
        assert r.status_code == 200 and r.content.startswith(b"piper/b/Hello!")


@pytestmark_api
async def test_api_limits(test_db, fake_registry, monkeypatch):
    from app.auth import ratelimit

    async with signed_in(_app()) as c:
        too_long = "x" * (get_settings().tts_max_chars + 1)
        r = await c.post("/api/tts/speak", json={"text": too_long, "voice": "piper:a"})
        assert r.status_code == 413
        monkeypatch.setattr(get_settings(), "tts_rate_limit", 2)
        ratelimit.reset(f"tts:{c.user['id']}")
        codes = [(await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "piper:a"})).status_code for _ in range(3)]
        assert codes == [200, 200, 429]


@pytestmark_api
async def test_api_falls_back_to_browser_when_nothing_can_speak(test_db, monkeypatch):
    reg = _registry(Fake("piper", fail=True))
    monkeypatch.setattr("app.api.tts.get_registry", lambda: reg)
    async with signed_in(_app()) as c:
        r = await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "piper:a"})
        assert r.status_code == 503 and r.json()["fallback"] == "browser"
        assert "this device's voices" in r.json()["detail"]


# ---------- real Piper (opt-in) ----------


@pytest.mark.skipif(os.environ.get("BOOKMIND_TEST_PIPER") != "1", reason="set BOOKMIND_TEST_PIPER=1 (loads a voice)")
@pytest.mark.asyncio
async def test_real_piper_voice_speaks():
    from app.tts.piper import PiperProvider

    p = PiperProvider(get_settings())
    info = await p.info()
    if not info.available:
        pytest.skip(info.reason)
    key = info.voices[0].id.partition(":")[2]
    normal = await p.synthesize("The fox waited for spring.", key, 1.0)
    fast = await p.synthesize("The fox waited for spring.", key, 2.0)
    assert normal.data[:4] == b"RIFF" and len(fast.data) < len(normal.data) * 0.75
