"""A nav badge says what its page says, or says nothing (CPO review, 2026-10-31).

/api/nav/badges read `precomputed.load(...) or {}` and then
`metrics.get(key, 0)`, so a payload refused by the staleness guard
produced 0 -- while the page it links to fell through to a live compute
and showed the real count. The badge contradicted the page it exists to
summarise, and 0 is the one value that reads as "nothing to do here".
"""

from src import badges, cache

TENANT = "CUST-0000"
PAYLOAD = {"metrics": {"review_count": 9, "unmatched": 3, "high": 2}}


def test_a_precomputed_payload_is_used(monkeypatch):
    monkeypatch.setattr("src.precompute_store.get", lambda key: PAYLOAD)
    assert badges.badge_metrics(TENANT, "invoices_pending", "invoices") \
        == PAYLOAD["metrics"]


def test_a_refused_payload_falls_through_to_the_pages_own_cache(monkeypatch):
    # Exactly what the page does: precompute, then the live-path cache.
    monkeypatch.setattr("src.precompute_store.get", lambda key: None)
    cache.set(f"invoices:{TENANT}", PAYLOAD)
    try:
        assert badges.badge_metrics(TENANT, "invoices_pending", "invoices") \
            == PAYLOAD["metrics"]
    finally:
        cache.delete(f"invoices:{TENANT}")


def test_nothing_anywhere_is_unknown_and_not_zero(monkeypatch):
    monkeypatch.setattr("src.precompute_store.get", lambda key: None)
    assert badges.badge_metrics(TENANT, "invoices_pending", "invoices") is None, \
        "0 would read as 'nothing to review' beside a page showing nine"
