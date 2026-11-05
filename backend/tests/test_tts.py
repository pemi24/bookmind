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
from app.tts.encode import mp3_available
from tests.conftest import signed_in

needs_lameenc = pytest.mark.skipif(not mp3_available(), reason="lameenc isn't installed")

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


def test_sentences_of_a_very_long_chapter_are_fast():
    # The reader asks for a whole chapter at once; splitting must stay linear in its length.
    import time

    chapter = ("Mr. Fox met Dr. Owl at 3.30 p.m. by the oak. They spoke of frost, of spring, of J. R. R. Tolkien. "
               "Was it late? It was.\n\n") * 4000  # ~500,000 characters
    started = time.perf_counter()
    sentences = split_sentences(chapter)
    assert len(sentences) == 4 * 4000
    assert time.perf_counter() - started < 3


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
async def test_google_pcm_becomes_wav_or_mp3():
    from app.tts.cloud import GoogleProvider

    pcm = b"\x00\x01" * 100
    body = {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    s = get_settings().model_copy(update={"gemini_api_key": "g", "tts_audio_format": "wav"})
    audio = await GoogleProvider(s, httpx.MockTransport(lambda r: httpx.Response(200, json=body))).synthesize("Hi.", "Kore")
    assert audio.mime == "audio/wav" and audio.data.startswith(b"RIFF") and audio.data.endswith(pcm)
    if mp3_available():
        s = s.model_copy(update={"tts_audio_format": "mp3"})
        audio = await GoogleProvider(s, httpx.MockTransport(lambda r: httpx.Response(200, json=body))).synthesize("Hi.", "Kore")
        assert audio.mime == "audio/mpeg" and _lame_tag(audio.data)["rate"] == 24000


# ---------- compressed audio ----------


def _speechlike(seconds: float, rate: int = 22050) -> bytes:
    """Mono 16-bit PCM that isn't trivially compressible: a wobbling tone with noise."""
    import math
    import random
    import struct

    rnd = random.Random(1)
    n = int(round(seconds * rate))
    return b"".join(struct.pack("<h", int(6000 * math.sin(i * (0.05 + 0.02 * math.sin(i / 3000))) + rnd.randint(-800, 800)))
                    for i in range(n))


def _lame_tag(mp3: bytes) -> dict:
    """What a browser reads from the Info frame: frame count, size, encoder delay and padding."""
    from app.tts.encode import _crc16, _frame

    size, per_frame, rate, side = _frame(mp3[:4])
    t = 4 + side
    assert mp3[t:t + 4] == b"Info" and mp3[t + 120:t + 129] == b"LAME3.100"
    lame = t + 120
    v = int.from_bytes(mp3[lame + 21:lame + 24], "big")
    assert int.from_bytes(mp3[lame + 34:lame + 36], "big") == _crc16(mp3[:lame + 34])  # tag CRC
    assert int.from_bytes(mp3[lame + 32:lame + 34], "big") == _crc16(mp3[size:])  # music CRC
    frames, at = 0, size
    while at < len(mp3):
        at += _frame(mp3[at:at + 4])[0]
        frames += 1
    assert at == len(mp3)
    return {"frames": int.from_bytes(mp3[t + 8:t + 12], "big"), "counted": frames, "per_frame": per_frame, "rate": rate,
            "bytes": int.from_bytes(mp3[t + 12:t + 16], "big"), "delay": v >> 12, "padding": v & 0xFFF}


@needs_lameenc
def test_mp3_is_much_smaller_and_records_its_exact_length():
    from app.tts.base import wav_bytes
    from app.tts.encode import pcm_audio

    pcm = _speechlike(3.0)
    audio = pcm_audio(pcm, 22050, "mp3", 40)
    assert audio.mime == "audio/mpeg"
    assert len(wav_bytes(pcm, 22050)) / len(audio.data) > 8
    tag = _lame_tag(audio.data)
    assert tag["frames"] == tag["counted"] and tag["bytes"] == len(audio.data) and tag["rate"] == 22050
    # decoders drop the delay and padding: what's left is exactly the PCM that went in (gapless)
    assert tag["delay"] == 576 and tag["frames"] * tag["per_frame"] - tag["delay"] - tag["padding"] == len(pcm) // 2


@needs_lameenc
def test_mp3_of_a_very_short_clip_and_other_rates():
    from app.tts.encode import pcm_audio

    for rate, samples in ((22050, 1), (16000, 700), (24000, 24000), (44100, 5000)):
        tag = _lame_tag(pcm_audio(_speechlike(samples / rate, rate), rate, "mp3", 40).data)
        assert tag["rate"] == rate
        assert tag["frames"] * tag["per_frame"] - tag["delay"] - tag["padding"] == samples


def test_wav_when_asked_or_when_lameenc_is_missing(monkeypatch):
    from app.tts import encode

    pcm = _speechlike(0.2)
    assert encode.pcm_audio(pcm, 22050, "wav").mime == "audio/wav"
    monkeypatch.setattr(encode, "mp3_available", lambda: False)
    audio = encode.pcm_audio(pcm, 22050, "mp3")
    assert audio.mime == "audio/wav" and audio.data.startswith(b"RIFF") and audio.data.endswith(pcm)

    def broken(*a, **k):
        raise ValueError("odd sample rate")

    monkeypatch.setattr(encode, "mp3_available", lambda: True)
    monkeypatch.setattr(encode, "encode_mp3", broken)
    assert encode.pcm_audio(pcm, 22050, "mp3").mime == "audio/wav"  # still plays


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
        # different sentences: the same one again would come from the cache, which isn't limited
        codes = [(await c.post("/api/tts/speak", json={"text": f"Hi {n}.", "voice": "piper:a"})).status_code for n in range(3)]
        assert codes == [200, 200, 429]


@pytestmark_api
async def test_api_falls_back_to_browser_when_nothing_can_speak(test_db, monkeypatch):
    reg = _registry(Fake("piper", fail=True))
    monkeypatch.setattr("app.api.tts.get_registry", lambda: reg)
    async with signed_in(_app()) as c:
        r = await c.post("/api/tts/speak", json={"text": "Hi.", "voice": "piper:a"})
        assert r.status_code == 503 and r.json()["fallback"] == "browser"
        assert "this device's voices" in r.json()["detail"]


@pytestmark_api
async def test_voice_preferences_are_saved_per_account(test_db):
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        prefs = {"tts_chat_voice": "piper:en_GB-alba-medium", "tts_read_voice": "browser:Microsoft Zira - English",
                 "tts_speed": 1.25, "tts_pitch": 0.9, "tts_volume": 0.8, "tts_auto_read": True}
        r = await a.patch("/api/account/preferences", json=prefs)
        assert r.status_code == 200 and {k: r.json()["user"]["settings"][k] for k in prefs} == prefs
        assert {k: (await a.get("/api/auth/me")).json()["user"]["settings"][k] for k in prefs} == prefs
        # other preferences are untouched, and other accounts keep their own
        assert (await a.patch("/api/account/preferences", json={"theme": "dark"})).json()["user"]["settings"]["tts_speed"] == 1.25
        assert "tts_chat_voice" not in (await b.get("/api/auth/me")).json()["user"]["settings"]
        # "" = back to the server's default voice
        r = await a.patch("/api/account/preferences", json={"tts_chat_voice": ""})
        assert r.json()["user"]["settings"]["tts_chat_voice"] == ""
        for bad in ({"tts_chat_voice": "skynet:hal"}, {"tts_read_voice": "piper"}, {"tts_speed": 3},
                    {"tts_volume": -1}, {"tts_chat_voice": "piper:a\nb"}):
            assert (await a.patch("/api/account/preferences", json=bad)).status_code == 422, bad


CHAPTER = ("Mr. Fox woke early. The frost was thick!\n\n"
           "He waited by the oak,\nwatching the snow. Was spring near?\n\n"
           "* * *\n\n"
           "It was.")


async def _book_with_chapters(user_id: int) -> tuple[int, list[int]]:
    from tests.test_account import _add_book
    from app.db.models import Chapter
    from app.db.session import SessionLocal

    book_id = await _add_book(user_id, title="The Winter Fox")
    async with SessionLocal() as db:
        chapters = [Chapter(book_id=book_id, position=1, title="Frost", text=CHAPTER, page_map=[]),
                    Chapter(book_id=book_id, position=2, title="Spring", text="Spring came.", page_map=[])]
        db.add_all(chapters)
        await db.commit()
        return book_id, [c.id for c in chapters]


@pytestmark_api
async def test_chapter_sentences_with_offsets_and_paragraphs(test_db):
    async with signed_in(_app()) as a:
        _, (ch1, _) = await _book_with_chapters(a.user["id"])
        r = await a.get(f"/api/tts/chapters/{ch1}/sentences")
        assert r.status_code == 200
        body = r.json()
        assert (body["position"], body["title"]) == (1, "Frost")
        got = body["sentences"]
        assert [s["text"] for s in got] == [
            "Mr. Fox woke early.", "The frost was thick!", "He waited by the oak, watching the snow.",
            "Was spring near?", "It was."]
        paragraph_starts = [0, CHAPTER.index("He waited"), CHAPTER.index("It was.")]
        assert [s["p"] for s in got] == [paragraph_starts[i] for i in (0, 0, 1, 1, 2)]
        for s in got:
            assert " ".join(CHAPTER[s["start"]:s["end"]].split()) == s["text"]


@pytestmark_api
async def test_listening_position_is_saved_and_private(test_db):
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        book_id, (ch1, ch2) = await _book_with_chapters(a.user["id"])
        assert (await a.get(f"/api/books/{book_id}")).json()["listening"] is None
        r = await a.put(f"/api/tts/books/{book_id}/listening", json={"position": 2, "offset": 7})
        assert r.status_code == 200 and (r.json()["position"], r.json()["offset"]) == (2, 7)
        assert (await a.get(f"/api/books/{book_id}")).json()["listening"]["position"] == 2
        # the reading bookmark is separate
        assert (await a.get(f"/api/books/{book_id}")).json()["reading"] is None
        assert (await a.put(f"/api/tts/books/{book_id}/listening", json={"position": 9})).status_code == 400

        # someone else: 404 for the book, its chapters' text and its position
        assert (await b.get(f"/api/tts/chapters/{ch1}/sentences")).status_code == 404
        assert (await b.put(f"/api/tts/books/{book_id}/listening", json={"position": 1})).status_code == 404
        assert (await b.delete(f"/api/tts/books/{book_id}/listening")).status_code == 404
        assert (await a.get(f"/api/books/{book_id}")).json()["listening"]["position"] == 2

        assert (await a.delete(f"/api/tts/books/{book_id}/listening")).status_code == 204
        assert (await a.get(f"/api/books/{book_id}")).json()["listening"] is None


# ---------- audio cache ----------


@pytestmark_api
async def test_cache_hits_skip_synthesis(test_db, fake_registry):
    piper = fake_registry.providers["piper"]
    async with signed_in(_app()) as a:
        say = lambda **kw: a.post("/api/tts/speak", json={"text": "The fox waited.", "voice": "piper:b", **kw})  # noqa: E731
        first, again = await say(), await say()
        assert first.headers["x-tts-cache"] == "miss" and again.headers["x-tts-cache"] == "hit"
        assert again.content == first.content and again.headers["content-type"] == "audio/wav"
        assert len(piper.calls) == 1
        # another speed or voice is another recording; a non-default volume is never cached
        assert (await say(speed=1.5)).headers["x-tts-cache"] == "miss"
        assert (await say(speed=1.5)).headers["x-tts-cache"] == "hit"
        assert (await a.post("/api/tts/speak", json={"text": "The fox waited.", "voice": "piper:a"})).headers["x-tts-cache"] == "miss"
        assert (await say(volume=0.5)).headers["x-tts-cache"] == "miss"
        assert (await say(volume=0.5)).headers["x-tts-cache"] == "miss"
        assert len(piper.calls) == 5
        # previews are cached the same way
        assert (await a.get("/api/tts/preview", params={"voice": "piper:b"})).headers["x-tts-cache"] == "miss"
        assert (await a.get("/api/tts/preview", params={"voice": "piper:b"})).headers["x-tts-cache"] == "hit"


@pytestmark_api
async def test_cache_hits_dont_count_toward_the_rate_limit(test_db, fake_registry, monkeypatch):
    from app.auth import ratelimit

    async with signed_in(_app()) as a:
        monkeypatch.setattr(get_settings(), "tts_rate_limit", 1)
        ratelimit.reset(f"tts:{a.user['id']}")
        say = lambda text: a.post("/api/tts/speak", json={"text": text, "voice": "piper:a"})  # noqa: E731
        assert (await say("One.")).status_code == 200
        assert [(await say("One.")).status_code for _ in range(3)] == [200, 200, 200]  # all from the cache
        assert (await say("Two.")).status_code == 429


@pytestmark_api
async def test_cache_is_per_user(test_db, fake_registry):
    from app.db.models import AudioCacheEntry
    from app.db.session import SessionLocal
    from app.tts import cache as audio_cache
    from sqlalchemy import select

    piper = fake_registry.providers["piper"]
    async with signed_in(_app()) as a, signed_in(_app()) as b:
        text = "A sentence both of them hear."
        await a.post("/api/tts/speak", json={"text": text, "voice": "piper:a"})
        r = await b.post("/api/tts/speak", json={"text": text, "voice": "piper:a"})
        assert r.headers["x-tts-cache"] == "miss" and len(piper.calls) == 2  # B never gets A's audio
        async with SessionLocal() as db:
            rows = (await db.execute(select(AudioCacheEntry).where(
                AudioCacheEntry.text_hash == audio_cache.key(text, 1)[0],
                AudioCacheEntry.user_id.in_([a.user["id"], b.user["id"]])))).scalars().all()
        assert sorted(r.user_id for r in rows) == sorted([a.user["id"], b.user["id"]])
        assert {r.path.split("/")[0] for r in rows} == {f"user-{a.user['id']}", f"user-{b.user['id']}"}
        # deleting an account deletes its cached audio
        assert audio_cache.user_dir(b.user["id"]).exists()
        assert (await b.post("/api/account/delete", json={"password": "correct horse battery"})).status_code == 200
        assert not audio_cache.user_dir(b.user["id"]).exists()
        async with SessionLocal() as db:
            assert not (await db.execute(select(AudioCacheEntry).where(AudioCacheEntry.user_id == b.user["id"]))).first()


@pytestmark_api
async def test_fallback_audio_is_cached_under_the_voice_that_spoke(test_db, fake_registry):
    async with signed_in(_app()) as a:
        r = await a.post("/api/tts/speak", json={"text": "Hello.", "voice": "cloud:a"})  # cloud fails → piper:a
        assert unquote(r.headers["x-tts-voice"]) == "piper:a"
        again = await a.post("/api/tts/speak", json={"text": "Hello.", "voice": "cloud:a"})
        assert again.headers["x-tts-cache"] == "miss"  # not served as if the cloud voice had said it
        assert (await a.post("/api/tts/speak", json={"text": "Hello.", "voice": "piper:a"})).headers["x-tts-cache"] == "hit"


@pytestmark_api
async def test_cache_prunes_old_and_least_recently_used(test_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, select, update

    from app.db.models import AudioCacheEntry
    from app.db.session import SessionLocal
    from app.tts import cache as audio_cache

    async with signed_in(_app()) as a:
        uid = a.user["id"]
        clip = Audio(b"\0" * 400_000, "audio/wav")
        async with SessionLocal() as db:
            await db.execute(delete(AudioCacheEntry))  # the test database's cache: only this test's entries count
            await db.commit()
            for n in range(4):
                await audio_cache.put(db, uid, "piper:a", 1.0, f"sentence {n}", clip)
            # sentence 0 hasn't been played for ages; sentence 1 was played just now
            await db.execute(update(AudioCacheEntry).where(AudioCacheEntry.user_id == uid,
                             AudioCacheEntry.text_hash == audio_cache.key("sentence 0", 1)[0])
                             .values(last_used_at=datetime.now(timezone.utc) - timedelta(days=400)))
            await db.commit()
            assert await audio_cache.get(db, uid, "piper:a", 1.0, "sentence 1")
            # 1.6 MB in the cache, limit 1 MB: the old one goes, then the least recently used until under 0.9 MB
            monkeypatch.setattr(get_settings(), "tts_cache_max_mb", 1)
            monkeypatch.setattr(get_settings(), "tts_cache_max_age_days", 60)
            removed, freed = await audio_cache.prune(db)
            left = {e.text_hash for e in (await db.execute(select(AudioCacheEntry).where(AudioCacheEntry.user_id == uid))).scalars()}
        assert audio_cache.key("sentence 0", 1)[0] not in left  # too old
        assert audio_cache.key("sentence 1", 1)[0] in left  # most recently played
        assert len(left) == 2 and (removed, freed) == (2, 800_000)
        files = list(audio_cache.user_dir(uid).iterdir())
        assert len(files) == 2


@pytestmark_api
async def test_cache_saves_mp3_as_mp3(test_db):
    from app.db.session import SessionLocal
    from app.tts import cache as audio_cache

    clip = Audio(b"\xff\xf3mp3", "audio/mpeg")
    async with signed_in(_app()) as a:
        uid = a.user["id"]
        async with SessionLocal() as db:
            await audio_cache.put(db, uid, "piper:a", 1.0, "An mp3 sentence.", clip)
            assert await audio_cache.get(db, uid, "piper:a", 1.0, "An mp3 sentence.") == clip
        assert [f.suffix for f in audio_cache.user_dir(uid).iterdir()] == [".mp3"]


@pytestmark_api
async def test_cache_entry_with_missing_file_is_synthesized_again(test_db, fake_registry):
    from app.tts import cache as audio_cache

    piper = fake_registry.providers["piper"]
    async with signed_in(_app()) as a:
        await a.post("/api/tts/speak", json={"text": "Gone soon.", "voice": "piper:a"})
        for f in audio_cache.user_dir(a.user["id"]).iterdir():
            f.unlink()
        r = await a.post("/api/tts/speak", json={"text": "Gone soon.", "voice": "piper:a"})
        assert r.status_code == 200 and r.headers["x-tts-cache"] == "miss" and len(piper.calls) == 2
        assert (await a.post("/api/tts/speak", json={"text": "Gone soon.", "voice": "piper:a"})).headers["x-tts-cache"] == "hit"


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
    if mp3_available() and get_settings().tts_audio_format == "mp3":
        assert normal.mime == "audio/mpeg" and _lame_tag(normal.data)["delay"] == 576
    else:
        assert normal.data[:4] == b"RIFF"
    assert len(fast.data) < len(normal.data) * 0.75
