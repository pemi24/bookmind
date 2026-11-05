"""Synthesized speech kept on disk, so a sentence heard before plays at once instead of being
synthesized again.

Entries are per user and keyed by (voice, speed, sha256 of the text): the voice id includes its
provider. Files live in TTS_CACHE_DIR/user-<id>/; the audio_cache table says which file is which,
how big it is and when it was last played. prune() removes files unused for longer than
TTS_CACHE_MAX_AGE_DAYS, then the least recently used ones while the cache is over TTS_CACHE_MAX_MB.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AudioCacheEntry
from app.tts.base import Audio

log = logging.getLogger("bookmind.tts")

_EXT = {"audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/ogg": ".ogg"}
_written_since_prune = 0  # bytes; a prune runs once enough new audio has been written


def _root() -> Path:
    return Path(get_settings().tts_cache_dir)


def user_dir(user_id: int) -> Path:
    return _root() / f"user-{user_id}"


def key(text: str, speed: float) -> tuple[str, float]:
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), round(speed, 2)


async def get(db: AsyncSession, user_id: int, voice: str, speed: float, text: str) -> Audio | None:
    """This user's saved audio for the text, or None. A row whose file has gone is dropped."""
    if not get_settings().tts_cache_enabled:
        return None
    text_hash, speed = key(text, speed)
    entry = await db.scalar(select(AudioCacheEntry).where(
        AudioCacheEntry.user_id == user_id, AudioCacheEntry.voice == voice,
        AudioCacheEntry.speed == speed, AudioCacheEntry.text_hash == text_hash))
    if entry is None:
        return None
    try:
        data = (_root() / entry.path).read_bytes()
    except OSError:
        await db.delete(entry)
        await db.commit()
        return None
    await db.execute(update(AudioCacheEntry).where(AudioCacheEntry.id == entry.id).values(last_used_at=func.now()))
    await db.commit()
    return Audio(data, entry.mime)


async def put(db: AsyncSession, user_id: int, voice: str, speed: float, text: str, audio: Audio) -> None:
    """Save audio for later. Two identical requests at once keep the first one's file."""
    global _written_since_prune
    s = get_settings()
    if not s.tts_cache_enabled or s.tts_cache_max_mb <= 0:
        return
    text_hash, speed = key(text, speed)
    folder = user_dir(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{text_hash[:16]}-{uuid.uuid4().hex[:8]}{_EXT.get(audio.mime, '.bin')}"
    tmp = folder / (name + ".part")
    tmp.write_bytes(audio.data)
    os.replace(tmp, folder / name)  # never a half-written file under the real name
    row = (await db.execute(
        insert(AudioCacheEntry)
        .values(user_id=user_id, provider=voice.partition(":")[0], voice=voice, speed=speed, text_hash=text_hash,
                mime=audio.mime, size_bytes=len(audio.data), path=f"{folder.name}/{name}")
        .on_conflict_do_nothing(constraint="uq_audio_cache_key")
        .returning(AudioCacheEntry.id)
    )).first()
    await db.commit()
    if row is None:  # someone else saved it first
        (folder / name).unlink(missing_ok=True)
        return
    _written_since_prune += len(audio.data)
    if _written_since_prune > max(5 * 2**20, s.tts_cache_max_mb * 2**20 // 20):
        await prune(db)


async def prune(db: AsyncSession) -> tuple[int, int]:
    """Remove old entries, then the least recently used while over the size limit.
    Returns (files removed, bytes freed)."""
    global _written_since_prune
    _written_since_prune = 0
    s = get_settings()
    doomed: list[AudioCacheEntry] = []
    if s.tts_cache_max_age_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=s.tts_cache_max_age_days)
        doomed += (await db.execute(select(AudioCacheEntry).where(AudioCacheEntry.last_used_at < cutoff))).scalars().all()
    limit = max(0, s.tts_cache_max_mb) * 2**20
    total = (await db.scalar(select(func.coalesce(func.sum(AudioCacheEntry.size_bytes), 0)))) - sum(e.size_bytes for e in doomed)
    if total > limit:
        target = limit * 0.9  # some room, so it doesn't prune again after every sentence
        old_ids = {e.id for e in doomed}
        rows = (await db.execute(select(AudioCacheEntry).order_by(AudioCacheEntry.last_used_at).limit(5000))).scalars()
        for e in rows:
            if total <= target:
                break
            if e.id in old_ids:
                continue
            doomed.append(e)
            total -= e.size_bytes
    if not doomed:
        return 0, 0
    await db.execute(delete(AudioCacheEntry).where(AudioCacheEntry.id.in_([e.id for e in doomed])))
    await db.commit()
    freed = 0
    for e in doomed:
        try:
            (_root() / e.path).unlink(missing_ok=True)
            freed += e.size_bytes
        except OSError:
            pass
    log.info("Audio cache: removed %d file(s), %.1f MB", len(doomed), freed / 2**20)
    return len(doomed), freed


def remove_user(user_id: int) -> None:
    """Delete a user's cached audio files (their rows go with the account, by cascade)."""
    shutil.rmtree(user_dir(user_id), ignore_errors=True)
