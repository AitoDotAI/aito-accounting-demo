"""An Aito that could not answer must not be stored as an answer of "nothing".

`match_all` swallows an AitoError into an empty page, and `_match_and_cache`
cached that for five minutes in L1 and in the shared L2 table: one Aito blip
showed every visitor, on every container, "no payments" until it expired
(td-20261105161953190031). The visitor still gets the same empty page for the
request that hit the failure -- turning it into an error is Antti's call --
but it is not stored, so the next request after Aito recovers computes, and
the visitors who were waiting on the failed attempt are answered at once.
"""

import os
import threading

os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")
os.environ.setdefault("CACHE_WATCH_SECONDS", "0")

import pytest                                              # noqa: E402

from src import app as app_module                           # noqa: E402
from src import cache                                       # noqa: E402
from src.aito_client import AitoError                       # noqa: E402
from src.cache_keys import page_cache_key                   # noqa: E402
from src.matching_service import MatchingUnavailable, match_all   # noqa: E402

TENANT = "CUST-0000"
GOOD = {"pairs": [{"bank_txn_id": "T-1", "invoice_id": "I-1", "matched_by": "aito",
                   "explanation": []}],
        "metrics": {"total": 1, "matched_by_aito": 1, "matched_by_reference": 0}}


class DownAito:
    def search(self, *args, **kwargs):
        raise AitoError("Connection refused")


class RecordingAito:
    """Stands in for the shared table and records what is written to it."""

    def __init__(self):
        self.written_keys = []

    def _request(self, method, path, json=None, **kwargs):
        if json and "key" in json:
            self.written_keys.append(json["key"])
        return {}

    def search(self, *args, **kwargs):
        return {"hits": []}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(app_module.precomputed, "load", lambda cid, name: None)
    shared = RecordingAito()
    monkeypatch.setattr(cache, "_aito", shared)
    cache._l1.clear()
    app_module._pairing_attempts.clear()
    yield shared
    cache._l1.clear()


def test_match_all_can_say_that_aito_was_unavailable_instead_of_returning_empty():
    with pytest.raises(MatchingUnavailable):
        match_all(DownAito(), customer_id=TENANT, raise_on_unavailable=True)


def test_match_all_still_returns_the_empty_page_for_callers_that_want_it():
    assert match_all(DownAito(), customer_id=TENANT)["pairs"] == []


def test_the_visitor_still_sees_the_empty_page_but_it_is_stored_nowhere(monkeypatch, isolated):
    monkeypatch.setattr(app_module, "match_all", lambda *a, **k: (_ for _ in ()).throw(
        MatchingUnavailable("Connection refused")))

    body = app_module.matching_pairs(customer_id=TENANT)

    assert body["pairs"] == [] and body["metrics"]["total"] == 0
    assert cache.get(page_cache_key("matching", TENANT)) is None, "L1 stored the blank page"
    assert isolated.written_keys == [], "the shared table stored the blank page"


def test_the_next_request_after_aito_recovers_computes_instead_of_serving_a_blank(monkeypatch):
    state = {"up": False, "runs": 0}

    def flaky(*args, **kwargs):
        state["runs"] += 1
        if not state["up"]:
            raise MatchingUnavailable("Connection refused")
        return dict(GOOD)

    monkeypatch.setattr(app_module, "match_all", flaky)
    assert app_module.matching_pairs(customer_id=TENANT)["pairs"] == []

    state["up"] = True
    recovered = app_module.matching_pairs(customer_id=TENANT)

    assert recovered["pairs"][0]["invoice_id"] == "I-1"
    assert state["runs"] == 2


def test_visitors_waiting_on_an_unavailable_attempt_are_answered_at_once(monkeypatch):
    runs = []

    def down(*args, **kwargs):
        runs.append(1)
        threading.Event().wait(0.3)
        raise MatchingUnavailable("Connection refused")

    monkeypatch.setattr(app_module, "match_all", down)
    results = []
    threads = [threading.Thread(
        target=lambda: results.append(app_module.matching_pairs(customer_id=TENANT)))
        for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(runs) == 1, f"{len(runs)} attempts for 4 visitors"
    assert [r["pairs"] for r in results] == [[]] * 4
