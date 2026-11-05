"""/api/nav/badges answers null, not 0, when it has no count to give.

tests/test_nav_badges_follow_the_page.py covers `badge_metrics`. This
covers the route's own job, which is to carry its None through to the
response instead of flattening it (CPO re-review, 2026-10-31).

See tests/test_matching_explain_endpoint.py for why the env vars are set
before the import.
"""

import os

os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")
os.environ.setdefault("CACHE_WATCH_SECONDS", "0")

import pytest                                              # noqa: E402

from src import app as app_module                           # noqa: E402

TENANT = "CUST-0000"


@pytest.fixture
def nothing_precomputed(monkeypatch):
    monkeypatch.setattr("src.precompute_store.get", lambda key: None)
    monkeypatch.setattr(app_module.cache, "get", lambda key: None)


@pytest.fixture
def precomputed_payload(monkeypatch):
    # matched_by_aito and a labelled pair are what the matching_pairs
    # staleness check requires; without them this payload is refused and
    # the badge is null, which is a different test.
    monkeypatch.setattr(
        "src.precompute_store.get",
        lambda key: {
            "metrics": {"review_count": 9, "unmatched": 3, "high": 2,
                        "matched_by_aito": 5},
            "pairs": [{"bank_txn_id": "T-1", "matched_by": "aito"}],
        },
    )


def test_counts_are_reported_when_they_exist(precomputed_payload):
    assert app_module.nav_badges(customer_id=TENANT) == {
        "invoices": 9, "matching": 3, "anomalies": 2,
    }


def test_every_count_is_null_when_there_is_nothing_to_read(nothing_precomputed):
    assert app_module.nav_badges(customer_id=TENANT) == {
        "invoices": None, "matching": None, "anomalies": None,
    }


def test_a_refused_payload_gives_null_rather_than_zero(monkeypatch):
    """The regression this guards: a payload the staleness check refuses.

    `load` returns None, the old code did `or {}` and `.get(key, 0)`, and
    the nav printed 0 beside a page that had fallen through to live and
    was showing real numbers.
    """
    monkeypatch.setattr(
        "src.precompute_store.get",
        lambda key: {"metrics": {"review_count": 9, "unmatched": 3, "high": 2}},
    )
    monkeypatch.setattr(app_module.cache, "get", lambda key: None)
    assert app_module.nav_badges(customer_id=TENANT)["matching"] is None, \
        "the matching payload predates ADR 0026 and is refused: 0 would be a claim"


def test_the_badges_read_the_same_keys_the_pages_write(monkeypatch):
    """In v2 mode the page keys carry `v2:`; the badges must ask for those."""
    monkeypatch.setattr("src.precompute_store.get", lambda key: None)
    monkeypatch.setattr(app_module, "_V2", "v2:")
    asked = []
    monkeypatch.setattr(app_module.cache, "get", lambda key: asked.append(key))

    app_module.nav_badges(customer_id=TENANT)

    assert sorted(asked) == [f"anomalies:v2:{TENANT}", f"invoices:v2:{TENANT}",
                             f"matching:v2:{TENANT}"]
