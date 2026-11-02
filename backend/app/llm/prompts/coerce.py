"""Lenient pre-validation for model output (small local models are sloppy with types/enums)."""
from __future__ import annotations

import re
from typing import Any

_WORDS = {"very low": 1, "low": 2, "minor": 2, "medium": 3, "moderate": 3, "high": 4, "major": 4,
          "very high": 5, "critical": 5, "central": 5}


def to_int(v: Any, lo: int, hi: int, default: int) -> int:
    """'4', 4.0, '4/5', 'high' -> clamped int."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return int(min(max(round(v), lo), hi))
    if isinstance(v, str):
        if v.strip().lower() in _WORDS:
            return min(max(_WORDS[v.strip().lower()], lo), hi)
        m = re.search(r"-?\d+", v)
        if m:
            return int(min(max(int(m.group()), lo), hi))
    return default


def to_list(v: Any) -> list:
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[,;]", v) if s.strip()]
    return list(v) if isinstance(v, (list, tuple)) else [v]


def to_str(v: Any) -> str:
    return "" if v is None else str(v)


def to_enum(v: Any, allowed: tuple[str, ...], synonyms: dict[str, str], default: str | None = None) -> Any:
    """Map free-form labels onto an enum; unknown values pass through so validation rejects them."""
    if not isinstance(v, str):
        return v
    key = re.sub(r"[\s\-/]+", "_", v.strip().lower())
    if key in allowed:
        return key
    if key in synonyms:
        return synonyms[key]
    for k, target in synonyms.items():
        if k in key:
            return target
    return default if default is not None else v
