"""Per-scope cache versions, so a container notices a rebuild by itself.

A running container pins precompute payloads in L1 for its lifetime
(`precompute_store`), so `./do precompute-v2` is invisible to it until
something drops them. ADR 0022 added a manual endpoint; this is the part
that does not need remembering.

One row per scope, holding the second at which that scope was last
written. Writers bump what they touched; readers compare against what
they last saw. See ADR 0023.
"""

import time

from src.aito_client import AitoClient, AitoError

VERSIONS_TABLE = "cache_versions"
VERSIONS_SCHEMA = {
    "type": "table",
    "columns": {
        # "table:invoices" or "precompute:matching_pairs". The prefix says
        # how far the invalidation reaches: a table underlies every derived
        # view, a precompute view only itself.
        "scope":   {"type": "String", "nullable": False},
        "version": {"type": "Int", "nullable": False},
    },
}

TABLE_PREFIX = "table:"
PRECOMPUTE_PREFIX = "precompute:"

_aito: AitoClient | None = None


def init(client: AitoClient) -> None:
    """Wire up the client and ensure the table exists.

    Non-fatal on failure, like `precompute_store.init`: a demo that cannot
    reach Aito should still serve its bootstrap JSON rather than refuse to
    start.
    """
    global _aito
    _aito = client
    try:
        client._request("PUT", f"/schema/{VERSIONS_TABLE}", json=VERSIONS_SCHEMA)
    except AitoError:
        # Aito returns 4xx on a duplicate-table PUT.
        pass


def bump(scopes: list[str], *, now: int | None = None) -> None:
    """Record that `scopes` were just written. Callers are the build scripts.

    Best-effort by design: a precompute run that cannot reach the versions
    table has still written its payloads, and failing the run for a cache
    hint would be the tail wagging the dog. A container then picks the
    change up on its next restart, which is the behaviour we had before.
    """
    if _aito is None or not scopes:
        return
    stamp = int(time.time()) if now is None else now
    for scope in scopes:
        try:
            # Delete-then-insert: the same upsert shape `precompute_store`
            # uses, for the same reason (no native upsert primitive yet).
            _aito._request("POST", "/data/_delete",
                           json={"from": VERSIONS_TABLE, "where": {"scope": scope}})
        except AitoError:
            pass
        try:
            _aito._request("POST", f"/data/{VERSIONS_TABLE}",
                           json={"scope": scope, "version": stamp})
        except AitoError:
            pass


def current() -> dict[str, int]:
    """Every scope's version, in one query.

    One small query is the whole point: polling the payloads themselves
    costs about as much as reading one (0.8-5.2 s measured), so the check
    has to be a single cheap read or it cannot run periodically at all.

    Returns {} when Aito is unreachable, which a caller must read as "no
    information" rather than "nothing changed" — see `changed_since`.
    """
    if _aito is None:
        return {}
    try:
        result = _aito.search(VERSIONS_TABLE, {}, limit=1000)
    except AitoError:
        return {}
    return {h["scope"]: h["version"] for h in result.get("hits", [])
            if "scope" in h and "version" in h}


def changed_since(snapshot: dict[str, int], latest: dict[str, int]) -> set[str]:
    """Scopes whose version moved, or that appeared for the first time.

    A scope missing from `latest` is NOT reported as changed: an empty or
    partial read means Aito was unreachable or the table was never
    written, and treating absence as a change would drop every cache on
    every failed poll — turning a transient outage into a recompute storm.
    """
    changed = set()
    for scope, version in latest.items():
        if snapshot.get(scope) != version:
            changed.add(scope)
    return changed
