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


def test_a_refused_cache_entry_is_evicted_so_the_next_ask_recomputes():
    # Otherwise the 409 is sticky for the whole 300 s TTL even once the
    # page has been reloaded and agrees with the ledger again.
    _cache_an_explanation("INV-1")
    with pytest.raises(HTTPException):
        app_module.matching_explain(
            customer_id=TENANT, transaction_id=TXN, invoice_id="INV-2")
    assert cache.get(f"matching_why:{V2}{TENANT}:{TXN}") is None


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
