"""Two-layer cache: in-memory for speed, Aito for persistence.

Layer 1: In-memory dict with TTL — instant reads, cleared on restart.
Layer 2: Aito prediction_cache table — survives restarts, analyzable
via _relate, and demonstrates Aito as both prediction engine and
prediction store.

On get: check memory → check Aito → miss.
On set: write to memory AND to Aito (background).
"""

import hashlib
import json
import time
import threading
from typing import Any

from src.aito_client import AitoClient, AitoError

# ── Layer 1: In-memory TTL cache ──────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 600  # 10 minutes

# ── Layer 2: Aito persistent cache ────────────────────────────────

_aito_client: AitoClient | None = None

CACHE_TABLE = "prediction_cache"
CACHE_SCHEMA = {
    "type": "table",
    "columns": {
        "cache_key": {"type": "String", "nullable": False},
        "endpoint": {"type": "String", "nullable": False},
        "response_json": {"type": "String", "nullable": False},
        "created_at": {"type": "String", "nullable": False},
    },
}


def init_persistent_cache(client: AitoClient) -> None:
    """Initialize persistent cache with Aito client and ensure table exists."""
    global _aito_client
    _aito_client = client

    try:
        schema = client.get_schema()
        if CACHE_TABLE not in schema.get("schema", {}):
            client._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
            print(f"  Created {CACHE_TABLE} table in Aito.")
    except AitoError as e:
        print(f"  Could not create cache table: {e}")


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get(key: str) -> Any | None:
    """Check memory first, then Aito."""
    # Layer 1: memory
    entry = _cache.get(key)
    if entry is not None:
        expires_at, value = entry
        if time.monotonic() <= expires_at:
            return value
        del _cache[key]

    # Layer 2: Aito
    if _aito_client is not None:
        try:
            result = _aito_client.search(
                CACHE_TABLE,
                {"cache_key": _key_hash(key)},
                limit=1,
            )
            hits = result.get("hits", [])
            if hits:
                value = json.loads(hits[0]["response_json"])
                # Promote to memory cache
                _cache[key] = (time.monotonic() + DEFAULT_TTL, value)
                return value
        except (AitoError, json.JSONDecodeError, KeyError):
            pass

    return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Write to memory and persist to Aito in background."""
    _cache[key] = (time.monotonic() + ttl, value)

    if _aito_client is not None:
        def persist():
            try:
                import datetime
                record = {
                    "cache_key": _key_hash(key),
                    "endpoint": key.split(":")[0] if ":" in key else key,
                    "response_json": json.dumps(value, default=str),
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                _aito_client._request("POST", f"/data/{CACHE_TABLE}", json=record)
            except AitoError:
                pass  # Persistence failure is not critical
        threading.Thread(target=persist, daemon=True).start()


def clear() -> None:
    """Clear in-memory cache. Aito cache persists intentionally."""
    _cache.clear()
