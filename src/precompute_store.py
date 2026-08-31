"""Aito-backed precompute store.

The deploy story for this demo used to be: `./do precompute` writes
JSON into `data/precomputed/`, the docker image copies that into the
container at build time, and read endpoints serve from those files.
That works until git-vs-docker drift puts the wrong files in the
wrong image. Symptoms: empty home page, half the per-customer pages
broken, no good way to refresh precompute without a full rebuild.

This module routes precompute output through Aito itself instead.
The build pipeline writes to a `precompute_entries` table, the
running container reads from there on first hit. Same database that
serves predictions is now the cache for the demo's projections.

Read order:

1. **L1** in-process dict — microsecond access, populated on first
   read, dropped on container restart.
2. **Aito** `precompute_entries` table — durable, written by
   `./do precompute`, the source of truth for "current precompute
   state". A few-hundred-ms read.
3. **Local JSON** at `data/precomputed/{name}.json` — bootstrap
   fallback for two cases: (a) `./do dev` against a fresh local
   Aito with no precompute table yet; (b) Aito briefly unreachable
   in production. Two files (`landing.json`, `help_related.json`)
   are checked into git for exactly this reason.
4. `None` — caller decides whether to fall back further (e.g. live
   computation) or to surface an error.

Writes only happen from `./do precompute`. Endpoints never write.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from src.aito_client import AitoClient, AitoError

PRECOMPUTE_TABLE = "precompute_entries"
PRECOMPUTE_SCHEMA = {
    "type": "table",
    "columns": {
        "name":        {"type": "String", "nullable": False},
        "payload":     {"type": "Text",   "nullable": False},
        "computed_at": {"type": "Int",    "nullable": False},
    },
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_DIR = _PROJECT_ROOT / "data" / "precomputed"

# Precompute derived from the v2 API lives in its own namespace, because
# a projection is only valid for the API generation that produced it.
# Without this, a v2 deployment reads v1-derived JSON and shows numbers
# that no v2 query would return — silently, since the payload is
# well-formed either way. The prefix mirrors the `_V2` cache-key prefix
# in app.py, for the same reason.
#
# Read at import time from the same variable that selects the v2 client,
# so `./do precompute --v2` writes where `./do dev-v2` reads.
_NAMESPACE = "v2:" if os.environ.get("AITO_V2_ENV", "").strip() else ""


def namespace() -> str:
    """The active precompute namespace (`""` on v1, `"v2:"` on v2)."""
    return _NAMESPACE

_aito: AitoClient | None = None
_l1: dict[str, Any] = {}
_l1_mutex = threading.Lock()


def per_customer_key(customer_id: str, name: str) -> str:
    """Namespace per-customer precomputes so the table stays flat
    while reads/writes still scope correctly."""
    return f"cust:{customer_id}:{name}"


def bootstrap_path(name: str) -> Path:
    """Where the bootstrap JSON for `name` lives, in the active namespace.

    `./do precompute` writes here as well as to Aito, so it has to agree
    with where `get()` later looks. One function knows the layout.
    """
    return _fallback_path(_NAMESPACE + name)


def _fallback_path(name: str) -> Path:
    """Map a precompute key to its bootstrap JSON path on disk.

    Per-customer keys (`cust:CUST-0000:invoices_pending`) live in
    `data/precomputed/CUST-0000/invoices_pending.json`. Cross-tenant
    keys (`landing`) live in `data/precomputed/landing.json`.

    v2-namespaced keys get their own subtree (`data/precomputed/v2/...`)
    so a v2 precompute run cannot overwrite the v1 bootstrap files that
    are checked into git.
    """
    root = _FALLBACK_DIR
    if name.startswith("v2:"):
        root = _FALLBACK_DIR / "v2"
        name = name[len("v2:"):]
    if name.startswith("cust:"):
        _, cid, sub = name.split(":", 2)
        return root / cid / f"{sub}.json"
    return root / f"{name}.json"


def init(client: AitoClient) -> None:
    """Wire up the Aito client and ensure the table exists.

    Failures are non-fatal — the bootstrap JSON path still works
    when Aito is unreachable.
    """
    global _aito
    _aito = client
    try:
        client._request("PUT", f"/schema/{PRECOMPUTE_TABLE}", json=PRECOMPUTE_SCHEMA)
    except AitoError:
        # Table likely already exists — Aito returns 4xx on
        # duplicate-table PUTs.
        pass


def put(name: str, data: Any) -> None:
    """Upsert a precompute entry. Caller is `./do precompute`.

    Raises AitoError on failure so the precompute script can
    distinguish "wrote successfully" from "skipped".
    """
    if _aito is None:
        raise RuntimeError("precompute_store.init() not called")
    name = _NAMESPACE + name
    payload = json.dumps(data, ensure_ascii=False)
    # No native upsert primitive yet (Aito core has it merged to
    # main; ships next deploy). Until then: delete then insert.
    # Working delete URL is `/data/_delete` with `from` in the body
    # — `/data/{table}/delete` returns 404. See aito-core-message.md.
    try:
        _aito._request(
            "POST",
            "/data/_delete",
            json={"from": PRECOMPUTE_TABLE, "where": {"name": name}},
        )
    except AitoError:
        # Delete is best-effort — first-time writes will return total:0.
        pass
    _aito._request(
        "POST",
        f"/data/{PRECOMPUTE_TABLE}",
        json={"name": name, "payload": payload, "computed_at": int(time.time())},
    )
    # Refresh L1 so the writing process sees the new value too.
    with _l1_mutex:
        _l1[name] = data


def get(name: str) -> Any | None:
    """Read a precompute entry, falling back through L1 → Aito → file.

    None means "we couldn't find it anywhere" — the caller decides
    what to do (live compute, return empty, surface error).
    """
    name = _NAMESPACE + name

    # L1
    cached = _l1.get(name)
    if cached is not None:
        return cached

    # L2: Aito
    if _aito is not None:
        try:
            r = _aito.search(PRECOMPUTE_TABLE, {"name": name}, limit=1)
            hits = r.get("hits", [])
            if hits:
                value = json.loads(hits[0]["payload"])
                with _l1_mutex:
                    _l1[name] = value
                return value
        except (AitoError, KeyError, json.JSONDecodeError):
            # Fall through to the bootstrap file.
            pass

    # L3: local JSON bootstrap
    path = _fallback_path(name)
    if path.is_file():
        try:
            with open(path) as f:
                value = json.load(f)
            with _l1_mutex:
                _l1[name] = value
            return value
        except (OSError, json.JSONDecodeError):
            pass

    return None


def invalidate(name: str | None = None) -> None:
    """Drop L1 cache for a single name, or everything when name is None."""
    with _l1_mutex:
        if name is None:
            _l1.clear()
        else:
            _l1.pop(_NAMESPACE + name, None)
