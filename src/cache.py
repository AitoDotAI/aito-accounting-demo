"""Simple in-memory TTL cache for Form Fill predictions.

Only used for the live formfill endpoint. All other views serve
pre-computed static JSON — no caching needed.
"""

import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}

DEFAULT_TTL = 3600  # 1 hour — demo data doesn't change


def get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None
    return value


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    _cache[key] = (time.monotonic() + ttl, value)


def clear() -> None:
    _cache.clear()
