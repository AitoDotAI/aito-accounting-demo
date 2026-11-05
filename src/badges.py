"""The counts the left nav prints, and the rule that they may be unknown.

Split out of `src/app.py` so it can be tested without importing the app,
which builds clients and starts the cache watcher on import.
"""

from src import cache, precomputed


def badge_metrics(customer_id: str, name: str, cache_key: str) -> dict | None:
    """The metrics block the page for `name` would itself show.

    Same order the page endpoints use: the precomputed payload, then the
    cache the live path writes. `None` when neither exists -- the
    precompute is absent or was refused as stale and nothing has computed
    a replacement yet.

    `None` is not zero, and the caller must not flatten it into one. A
    refused precompute makes the page fall through to a live compute and
    show real numbers, so a nav badge reading 0 next to a page reading 9
    is a worse answer than no badge at all.

    `cache_key` is the page's own key, built by the app's `page_cache_key`.
    The badge spells no key of its own, so it cannot drift from the page's.
    """
    payload = precomputed.load(customer_id, name)
    if payload is None:
        payload = cache.get(cache_key)
    if payload is None:
        return None
    return payload.get("metrics") or {}
