"""Every tenant's Rules view is precomputed, not only the headline one.

The precompute skips `_evaluate` for all but CUST-0000, because at 1M-row
scale that call tipped the server into 504s. Rule performance was bundled
into the same skip, but it never calls `_evaluate` -- it searches and
mines rules. So 19 of 20 tenants were served an empty Rules view, which
the use-case review saw as "only Tornio has rules".
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "precompute_predictions",
    Path(__file__).resolve().parent.parent / "data" / "precompute_predictions.py")
pp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pp)


@pytest.fixture
def recorded(monkeypatch):
    written: dict[str, object] = {}
    monkeypatch.setattr(pp, "save", lambda cid, name, data: written.__setitem__(name, data) or 0)
    monkeypatch.setattr(pp, "mine_rules_for_customer", lambda *a, **k: [])
    for fn in ("precompute_invoices_pending", "precompute_matching", "precompute_anomalies",
               "precompute_quality_overview", "precompute_rules", "precompute_prediction_accuracy"):
        monkeypatch.setattr(pp, fn, lambda *a, **k: {"stub": True})
    monkeypatch.setattr(pp, "precompute_rule_performance_for_customer",
                        lambda *a, **k: {"rules": [{"name": "Europress Group Oy -> 5100"}]})
    return written


def test_rule_performance_is_computed_when_evaluate_is_skipped(recorded):
    pp.precompute_one_customer(None, "CUST-0007", [], lite=False, skip_evaluate=True)

    assert recorded["rule_performance"] == {"rules": [{"name": "Europress Group Oy -> 5100"}]}


def test_evaluate_itself_is_still_skipped(recorded):
    """The skip exists for `_evaluate`; that part must not change."""
    pp.precompute_one_customer(None, "CUST-0007", [], lite=False, skip_evaluate=True)

    assert recorded["prediction_accuracy"] == pp.EMPTY_PREDICTION_ACCURACY


def test_lite_tenants_still_get_the_empty_stub(recorded):
    """`lite` is the 'just signed up, no patterns yet' persona -- deliberate."""
    pp.precompute_one_customer(None, "CUST-0200", [], lite=True, skip_evaluate=True)

    assert recorded["rule_performance"] == pp.EMPTY_RULE_PERFORMANCE
