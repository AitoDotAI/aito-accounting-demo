"""Administrative operations, kept free of FastAPI and of app startup.

Separate from `app.py` for a reason worth stating: importing `src.app`
constructs live Aito clients and PUTs schemas at module level, so any
test that imports it stops being hermetic — it leaked into an unrelated
test's httpx mocking and made `test_formfill_service` assert 4 == 6.
Policy that needs testing therefore lives here, and `app.py` keeps only
the routing.
"""

import hmac
import os

from src import cache, cache_versions, precompute_store


class AdminDisabled(Exception):
    """No ADMIN_TOKEN is configured, so the operation does not exist."""


class AdminForbidden(Exception):
    """A token was required and the one supplied did not match."""


def check_admin_token(provided: str | None) -> None:
    """Authorize an administrative call, or raise.

    `AdminDisabled` when the deployment configured no token — the caller
    should answer 404 rather than 403, so a clean checkout exposes no
    administrative surface and a scan cannot tell the route from a typo.

    `AdminForbidden` when a token is required and the supplied one is
    missing or wrong. Compared with `hmac.compare_digest`, and never
    logged or echoed back.
    """
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise AdminDisabled
    if not provided or not hmac.compare_digest(provided, expected):
        raise AdminForbidden


def drop_in_process_caches() -> dict[str, int]:
    """Drop L1 so a rebuilt precompute becomes visible, and report counts.

    L1 is pinned for the process lifetime because a precompute payload is
    immutable for a given build — but not across builds. After
    `./do precompute-v2` writes L2, a running container keeps serving what
    it read before. See ADR 0022.

    Uses `cache.drop_local()`, NOT `cache.clear()`: clear() deletes and
    recreates the shared Aito `cache_entries` table, which other processes
    are reading. Reloading one container must not destroy everyone's L2.
    """
    return {
        "precompute_entries_dropped": precompute_store.invalidate(),
        "cache_entries_dropped": cache.drop_local(),
    }


def apply_version_changes(changed: set[str]) -> dict[str, int]:
    """Drop the caches a set of changed scopes invalidates. See ADR 0023.

    A changed TABLE underlies every derived view, so it drops everything.
    A changed PRECOMPUTE VIEW drops only that view, across customers —
    rebuilding one tenant's rules must not make the other nineteen
    recompute a matching page that did not change.

    The request cache is dropped whenever anything changed: its keys are
    view- and customer-shaped but not scope-shaped, and a stale answer
    there is the same defect by another route.
    """
    if not changed:
        return {"precompute_entries_dropped": 0, "cache_entries_dropped": 0}

    if any(s.startswith(cache_versions.TABLE_PREFIX) for s in changed):
        dropped = precompute_store.invalidate()
    else:
        dropped = sum(
            precompute_store.invalidate_view(s[len(cache_versions.PRECOMPUTE_PREFIX):])
            for s in changed
            if s.startswith(cache_versions.PRECOMPUTE_PREFIX)
        )
    return {
        "precompute_entries_dropped": dropped,
        "cache_entries_dropped": cache.drop_local(),
    }
