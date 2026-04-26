"""Two-layer cache: in-memory L1 + Aito persistent L2.

L1 (in-memory dict): microsecond access, lost on restart.
L2 (Aito cache_entries table): persists across restarts, tens-of-ms.

Read path: L1 hit → return; L2 hit → backfill L1, return; miss → None.
Write path: write both L1 and L2.

This demonstrates "Aito as a key-value store" — the same database
that serves predictions also persists the prediction cache.
"""

import json
import threading
import time
from typing import Any

from src.aito_client import AitoClient, AitoError

_l1: dict[str, tuple[float, Any]] = {}
_aito: AitoClient | None = None

# Per-key compute locks: when one request misses both L1 and L2 and
# starts computing, concurrent requests for the same key block on the
# same lock instead of triggering N independent computes.
#
# Usage:
#   with compute_lock(key):
#       cached = cache.get(key)
#       if cached: return cached
#       result = expensive_compute()
#       cache.set(key, result)
_locks_mutex = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def compute_lock(key: str) -> threading.Lock:
    """Return a per-key lock so concurrent misses share one compute.

    Caller must check the cache *inside* the lock to avoid duplicate
    work after the lock is acquired.
    """
    with _locks_mutex:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock

DEFAULT_TTL = 3600  # 1 hour — demo data doesn't change

CACHE_TABLE = "cache_entries"
CACHE_SCHEMA = {
    "type": "table",
    "columns": {
        "key": {"type": "String", "nullable": False},
        "value": {"type": "Text", "nullable": False},
        "created_at": {"type": "Int", "nullable": False},
        "ttl": {"type": "Int", "nullable": False},
    },
}


def init(client: AitoClient) -> None:
    """Initialize L2 cache with Aito client. Creates table if missing."""
    global _aito
    _aito = client
    try:
        client._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
    except AitoError:
        # Table likely exists; ignore
        pass


def get(key: str) -> Any | None:
    # L1
    entry = _l1.get(key)
    if entry is not None:
        expires_at, value = entry
        if time.monotonic() <= expires_at:
            return value
        del _l1[key]

    # L2
    if _aito is None:
        return None
    try:
        result = _aito.search(CACHE_TABLE, {"key": key}, limit=1)
        hits = result.get("hits", [])
        if not hits:
            return None
        row = hits[0]
        age = int(time.time()) - row["created_at"]
        if age > row["ttl"]:
            return None
        value = json.loads(row["value"])
        # Backfill L1 with remaining TTL
        remaining = max(1, row["ttl"] - age)
        _l1[key] = (time.monotonic() + remaining, value)
        return value
    except (AitoError, KeyError, json.JSONDecodeError):
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    # L1 always
    _l1[key] = (time.monotonic() + ttl, value)
    # L2 best-effort
    if _aito is None:
        return
    try:
        # Delete existing entry for this key, then insert (no native upsert)
        try:
            _aito._request("POST", f"/data/{CACHE_TABLE}/delete", json={"from": CACHE_TABLE, "where": {"key": key}})
        except AitoError:
            pass
        _aito._request("POST", f"/data/{CACHE_TABLE}", json={
            "key": key,
            "value": json.dumps(value, ensure_ascii=False),
            "created_at": int(time.time()),
            "ttl": ttl,
        })
    except (AitoError, TypeError):
        pass


def clear() -> None:
    _l1.clear()
    if _aito is not None:
        try:
            _aito._request("DELETE", f"/schema/{CACHE_TABLE}")
            _aito._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
        except AitoError:
            pass
