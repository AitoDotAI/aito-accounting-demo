"""The Quality endpoints refuse an empty tenant and never serve pre-fix cache entries."""

import pytest
from fastapi.testclient import TestClient

from src import cache
from src.app import _V2, app

client = TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/quality/evaluations?customer_id=",
    "/api/quality/evaluate?customer_id=&domain=invoices&predict=approver&input_fields=vendor",
])
def test_an_empty_customer_is_a_400_before_any_aito_call(path):
    assert client.get(path).status_code == 400


def test_evaluate_results_cached_before_the_scope_fix_are_not_served(monkeypatch):
    # Entries written by the unscoped build live ~10 minutes in L1 and in the
    # shared L2 table; the fix must not show them as if they were scoped.
    import src.evaluation_service as ev
    calls = []
    monkeypatch.setattr(ev, "run_evaluation",
                        lambda *a, **k: calls.append(a) or {"kpis": {"fresh": True}})
    tenant = "CUST-0127"  # a roster id when data/customers.json exists
    old_key = f"eval:{_V2}{tenant}:invoices:approver:vendor:100"
    cache.set(old_key, {"kpis": {"stale": True}})

    body = client.get(f"/api/quality/evaluate?customer_id={tenant}&domain=invoices"
                      "&predict=approver&input_fields=vendor&limit=100").json()

    assert body == {"kpis": {"fresh": True}}
    assert len(calls) == 1
