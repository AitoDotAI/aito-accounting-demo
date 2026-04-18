"""Simple in-memory TTL cache for API responses.

Demo predictions don't change unless the dataset changes, so caching
is safe and makes the UI feel responsive. Cache clears on server
restart or after TTL expires.
"""

import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}

DEFAULT_TTL = 300  # 5 minutes


def get(key: str) -> Any | None:
    """Return cached value if it exists and hasn't expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None
    return value


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Cache a value with TTL in seconds."""
    _cache[key] = (time.monotonic() + ttl, value)


def clear() -> None:
    """Clear all cached entries."""
    _cache.clear()
