"""Two-layer cache: in-memory L1 + Aito persistent L2.

L1 (in-memory dict): microsecond access, lost on restart.
L2 (Aito cache_entries table): persists across restarts, tens-of-ms.

Read path: L1 hit → return; L2 hit → backfill L1, return; miss → None.
Write path: write both L1 and L2.

This demonstrates "Aito as a key-value store" — the same database
that serves predictions also persists the prediction cache.
"""

import json
import sys
import threading
import time
from typing import Any

from src.aito_client import AitoClient, AitoError

_l1: dict[str, tuple[float, Any]] = {}
_aito: AitoClient | None = None

# L2 is best-effort: a failure falls back to L1 and the caller never knows.
# So that an operator can tell a broken shared table from a working one, the
# failures are counted and /healthz and /api/cache/status report them.
_l2_failures = {"writes": 0, "deletes": 0, "reads": 0}
_l2_last_error: str | None = None
_l2_mutex = threading.Lock()


def _l2_failed(kind: str, exc: Exception, path: str) -> None:
    """Count one failed L2 operation.

    /healthz is public, so what it reports is the error type, the HTTP status
    and the path -- never the body, which can echo request content. The full
    detail goes to stderr, once per kind: a table that rejects everything
    would otherwise bury the log, and the counters carry the rest.
    """
    global _l2_last_error
    with _l2_mutex:
        _l2_failures[kind] += 1
        first = _l2_failures[kind] == 1
        _l2_last_error = (f"{type(exc).__name__} status={getattr(exc, 'status_code', None)} "
                          f"{kind[:-1]} {path}")
    if first:
        body = str(getattr(exc, "body", "") or "")[:500]
        print(f"cache: first failed L2 {kind[:-1]} on {path} ({exc}) {body}; further "
              f"failures are counted in /healthz", file=sys.stderr)


def l2_health(with_last_error: bool = True) -> dict:
    """What the shared L2 table has been doing.

    `last_error` is process-wide, not per tenant, so a per-customer endpoint
    leaves it out.
    """
    health = {
        "configured": _aito is not None,
        "failed_writes": _l2_failures["writes"],
        "failed_deletes": _l2_failures["deletes"],
        "failed_reads": _l2_failures["reads"],
    }
    if with_last_error:
        health["last_error"] = _l2_last_error
    return health

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
    except AitoError as exc:
        # A 4xx is how a second PUT of an existing table answers. Anything
        # else (no connection, a 5xx) means L2 is down from the start.
        if exc.status_code is None or not 400 <= exc.status_code < 500:
            _l2_failed("writes", exc, f"/schema/{CACHE_TABLE}")


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
    except (AitoError, KeyError, json.JSONDecodeError) as exc:
        _l2_failed("reads", exc, "/_search")
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL, local_only: bool = False) -> None:
    """Cache `value`; `local_only` keeps it out of the shared L2 table.

    For what is cheap to rebuild and large to keep: it is not worth
    putting on the shared instance, and a miss only costs a recompute.
    """
    # L1 always
    _l1[key] = (time.monotonic() + ttl, value)
    # L2 best-effort
    if _aito is None or local_only:
        return
    try:
        # Delete existing entry for this key, then insert. The
        # working delete URL is `/data/_delete` (table goes in the
        # body's `from`, *not* in the path) — every reasonable
        # URL guess returns 404. See aito-core-message.md.
        # No native upsert primitive yet; aito core has it merged
        # to main and it ships in the next Aito deploy.
        try:
            _aito._request("POST", "/data/_delete", json={"from": CACHE_TABLE, "where": {"key": key}})
        except AitoError as exc:
            _l2_failed("deletes", exc, "/data/_delete")
        _aito._request("POST", f"/data/{CACHE_TABLE}", json={
            "key": key,
            "value": json.dumps(value, ensure_ascii=False),
            "created_at": int(time.time()),
            "ttl": ttl,
        })
    except (AitoError, TypeError) as exc:
        _l2_failed("writes", exc, f"/data/{CACHE_TABLE}")


def delete(key: str) -> None:
    """Forget one entry in both layers, so the next read recomputes it."""
    _l1.pop(key, None)
    if _aito is None:
        return
    try:
        _aito._request("POST", "/data/_delete",
                       json={"from": CACHE_TABLE, "where": {"key": key}})
    except AitoError as exc:
        # Best-effort like set(): an entry that survives in L2 still
        # expires on its TTL. Counted, so a broken L2 is visible.
        _l2_failed("deletes", exc, "/data/_delete")


def drop_local() -> int:
    """Drop the in-process copy only, leaving the shared Aito table alone.

    Distinct from `clear()` on purpose: `clear()` DELETEs and recreates
    `cache_entries`, which other processes are reading. Reloading one
    container's view must not destroy everyone else's cache.
    """
    n = len(_l1)
    _l1.clear()
    return n


def clear() -> None:
    _l1.clear()
    if _aito is not None:
        try:
            _aito._request("DELETE", f"/schema/{CACHE_TABLE}")
            _aito._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
        except AitoError:
            pass
