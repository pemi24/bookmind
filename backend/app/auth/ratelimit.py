"""In-memory rate limits for sign-in, sign-up and password reset (BookMind runs as one process).

Each limit counts attempts per key (an IP address, or an email address) in a sliding window.
Counting per email as well as per IP slows down guessing one account from many addresses, and
treats unknown emails exactly like real ones (no hint about who has an account).
"""
from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits: dict[str, deque[float]] = defaultdict(deque)


def _prune(q: deque[float], window: float, now: float) -> None:
    while q and q[0] <= now - window:
        q.popleft()


def check(key: str, limit: int, window: float, what: str = "attempts") -> None:
    """Count one attempt for `key`; 429 with a retry time once `limit` is reached within `window` seconds."""
    if limit <= 0:
        return
    now = time.monotonic()
    q = _hits[key]
    _prune(q, window, now)
    if len(q) >= limit:
        wait = max(1, math.ceil((q[0] + window - now) / 60))
        raise HTTPException(429, f"Too many {what}. Try again in {wait} minute{'s' if wait != 1 else ''}.")
    q.append(now)


def count(key: str, window: float) -> int:
    q = _hits[key]
    _prune(q, window, time.monotonic())
    return len(q)


def reset(key: str) -> None:
    _hits.pop(key, None)


def clear_all() -> None:  # tests
    _hits.clear()
