"""/api/matching/explain refuses to answer about another row's invoice.

The guard inside `explain_match` is covered by
tests/test_matching_explain_on_demand.py. This covers the two places the
ENDPOINT has to get right, which that file cannot see (CPO re-review,
2026-10-31: deleting either left all 315 tests green):

  app.py  the cached-payload check -- the cache holds whatever the
          pairing chose when it was written, which is the part that drifts
  app.py  passing expected_invoice_id through to explain_match at all

Importing src.app runs two startup warmups that call Aito, so
AITO_SKIP_STARTUP_WARMUP and CACHE_WATCH_SECONDS are set before the
import below. The route functions are called directly: FastAPI's Query
defaults are only consulted when it builds a request, so a plain keyword
call exercises the body.
"""

import os

os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")
os.environ.setdefault("CACHE_WATCH_SECONDS", "0")

import pytest                                              # noqa: E402
from fastapi import HTTPException                           # noqa: E402

from src import app as app_module                           # noqa: E402
from src import cache                                       # noqa: E402

TENANT = "CUST-0000"
TXN = "CUST-0000-TXN-000001"
V2 = app_module._V2


@pytest.fixture(autouse=True)
def _no_precompute_file(monkeypatch):
    # data/precomputed/ may hold this tenant's real page; these tests are
    # about the cache and the contexts, so no page is served unless a test says.
    monkeypatch.setattr(app_module.precomputed, "load", lambda cid, name: None)


@pytest.fixture(autouse=True)
def _clean_cache():
    for key in (f"matching_why:{V2}{TENANT}:{TXN}",
                f"matching_ctx:{V2}{TENANT}"):
        cache.delete(key)
    yield
    for key in (f"matching_why:{V2}{TENANT}:{TXN}",
                f"matching_ctx:{V2}{TENANT}"):
        cache.delete(key)


def _cache_an_explanation(invoice_id: str):
    cache.set(f"matching_why:{V2}{TENANT}:{TXN}",
              {"transaction_id": TXN, "invoice_id": invoice_id,
               "explanation": [{"type": "base", "target_value": invoice_id}]},
              ttl=300)


def test_a_cached_explanation_for_this_row_is_served():
    _cache_an_explanation("INV-1")
    payload = app_module.matching_explain(
        customer_id=TENANT, transaction_id=TXN, invoice_id="INV-1")
    assert payload["invoice_id"] == "INV-1"


def test_a_cached_explanation_for_another_invoice_is_refused():
    _cache_an_explanation("INV-1")
    with pytest.raises(HTTPException) as caught:
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-2")
    assert caught.value.status_code == 409
    assert "INV-2" in str(caught.value.detail)


def test_a_refused_ask_does_not_evict_the_cached_explanation():
    # A visitor's bogus invoice_id must not cost the real row its cache
    # entry, or one URL could keep every explanation cold.
    _cache_an_explanation("INV-1")
    with pytest.raises(HTTPException):
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-2")
    assert cache.get(f"matching_why:{V2}{TENANT}:{TXN}") is not None


def _serve_page(monkeypatch, pairs):
    """Put a page in front of the endpoint, as /api/matching/pairs would have."""
    monkeypatch.setattr(app_module.precomputed, "load", lambda cid, name: None)
    cache.set(f"matching:{V2}{TENANT}", {"pairs": pairs, "metrics": {}}, ttl=300)


@pytest.fixture
def no_recompute(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a bogus ask recomputed the pairing")
    monkeypatch.setattr(app_module, "_match_and_cache", refuse)
    monkeypatch.setattr(app_module, "explain_match", refuse)
    yield
    cache.delete(f"matching:{V2}{TENANT}")


def test_an_invoice_the_served_page_does_not_show_is_a_409_without_recomputing(monkeypatch, no_recompute):
    _serve_page(monkeypatch, [{"bank_txn_id": TXN, "invoice_id": "INV-1",
                               "matched_by": "aito", "explanation": []}])
    with pytest.raises(HTTPException) as caught:
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-BOGUS")
    assert caught.value.status_code == 409


def test_a_transaction_the_served_page_does_not_have_is_a_404_without_recomputing(monkeypatch, no_recompute):
    _serve_page(monkeypatch, [{"bank_txn_id": "OTHER", "invoice_id": "INV-1",
                               "matched_by": "aito", "explanation": []}])
    with pytest.raises(HTTPException) as caught:
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-1")
    assert caught.value.status_code == 404


def test_an_explanation_the_page_already_carries_is_served_without_aito(monkeypatch, no_recompute):
    inline = [{"type": "base", "target_value": "INV-1"}]
    _serve_page(monkeypatch, [{"bank_txn_id": TXN, "invoice_id": "INV-1",
                               "matched_by": "aito", "explanation": inline}])
    payload = app_module.matching_explain(
        customer_id=TENANT, transaction_id=TXN, invoice_id="INV-1")
    assert payload["explanation"] == inline


def test_the_rows_invoice_reaches_explain_match(monkeypatch):
    """The endpoint must pass expected_invoice_id down, not just accept it."""
    seen = {}

    def fake_explain_match(client, txn, open_invoices, invoice_id,
                           ranked_invoice_id=None, model_p=0.0,
                           expected_invoice_id=None):
        seen["expected"] = expected_invoice_id
        return [{"type": "base", "target_value": invoice_id}]

    monkeypatch.setattr(app_module, "explain_match", fake_explain_match)
    cache.set(f"matching_ctx:{V2}{TENANT}", {
        TXN: {"txn": {"txn_id": TXN}, "open_invoices": [{"invoice_id": "INV-1"}],
              "invoice_id": "INV-1", "ranked_invoice_id": None, "model_p": 0.9},
    }, ttl=300)

    app_module.matching_explain(
        customer_id=TENANT, transaction_id=TXN, invoice_id="INV-1")
    assert seen["expected"] == "INV-1", \
        "the endpoint accepted invoice_id and dropped it before the guard"


def test_a_transaction_with_no_aito_match_is_a_404(monkeypatch):
    monkeypatch.setattr(app_module, "_match_and_cache", lambda *a, **k: None)
    cache.set(f"matching_ctx:{V2}{TENANT}", {}, ttl=300)
    with pytest.raises(HTTPException) as caught:
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-1")
    assert caught.value.status_code == 404


def test_a_stale_cached_explanation_does_not_override_the_served_page(monkeypatch):
    # After a rebuild the page says INV-2 while an hour-long L2 entry still
    # explains INV-1. The page is what the user sees, so it decides: the stale
    # entry must not 409 a correct request, it is recomputed over.
    _serve_page(monkeypatch, [{"bank_txn_id": TXN, "invoice_id": "INV-2",
                               "matched_by": "aito", "explanation": []}])
    _cache_an_explanation("INV-1")
    cache.set(f"matching_ctx:{V2}{TENANT}", {
        TXN: {"txn": {"txn_id": TXN}, "open_invoices": [{"invoice_id": "INV-2"}],
              "invoice_id": "INV-2", "ranked_invoice_id": None, "model_p": 0.9},
    }, ttl=300)
    monkeypatch.setattr(app_module, "explain_match",
                        lambda *a, **k: [{"type": "base", "target_value": "INV-2"}])

    payload = app_module.matching_explain(
        customer_id=TENANT, transaction_id=TXN, invoice_id="INV-2")

    assert payload["invoice_id"] == "INV-2"
    cache.delete(f"matching:{V2}{TENANT}")
