"""The live smoke's content checks (scripts/verify_demo.py), offline.

Each case is the shape accounting.aito.ai returned on 2026-09-29, trimmed. The
point of the smoke is that it FAILS on a blank-but-200 view, so the failing
shapes are pinned as carefully as the passing ones.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "verify_demo", Path(__file__).resolve().parents[1] / "scripts" / "verify_demo.py")
vd = importlib.util.module_from_spec(_spec)
sys.modules["verify_demo"] = vd   # @dataclass looks its module up here
_spec.loader.exec_module(vd)


def _tenants(*gls):
    return [{"customer_id": f"CUST-{i:04d}", "gl_code": gl, "n": 10} for i, gl in enumerate(gls)]


def test_landing_needs_one_card_with_four_clients_and_four_accounts():
    # 29.9: the first card showed four clients but only three accounts
    first = {"vendor": "Schuravleff Oy", "tenants": _tenants("5400", "1600", "5400", "4600")}
    good = {"vendor": "Linkor Oy", "tenants": _tenants("5400", "1600", "4600", "6100")}
    summary = vd.check_multitenancy_landing({"vendors": [first, good]})
    assert "present Linkor Oy" in summary
    with pytest.raises(AssertionError, match="four different GL accounts"):
        vd.check_multitenancy_landing({"vendors": [first]})


def _row(confidence, why, source="aito"):
    return {"invoice_id": "X", "gl_code": "6100", "source": source, "confidence": confidence,
            "gl_alternatives": [{"why": why}]}


VISIBLE = {"type": "pattern", "lift": 5.25, "propositions": [{"field": "vendor", "value": "Nalco Oy"}]}
CATEGORY_LED = {"type": "pattern", "lift": 5.06,
                "propositions": [{"field": "category", "value": "software"}]}
TINY = {"type": "pattern", "lift": 1.05, "propositions": [{"field": "description", "value": "Oy"}]}


def test_invoices_pass_with_a_confident_explained_row_and_a_hesitant_one():
    body = {"invoices": [_row(0.96, [VISIBLE]), _row(0.60, [VISIBLE])]}
    assert "1 hesitant" in vd.check_invoices_pending(body)


def test_invoices_fail_when_nothing_hesitates():
    with pytest.raises(AssertionError, match="hesitates"):
        vd.check_invoices_pending({"invoices": [_row(0.96, [VISIBLE]), _row(0.99, [VISIBLE])]})


def test_invoices_fail_when_every_why_card_would_fold():
    # category- or amount-led and immaterial patterns fold into "other signals"
    rows = [_row(0.96, [CATEGORY_LED, TINY]), _row(0.60, [CATEGORY_LED])]
    with pytest.raises(AssertionError, match="why card"):
        vd.check_invoices_pending({"invoices": rows})


def test_cold_precompute_fails():
    with pytest.raises(AssertionError, match="matching_warm"):
        vd.check_cache_warm({"customer_id": "CUST-0001", "invoices_warm": True, "matching_warm": False})


def test_live_mode_never_runs_a_route_that_writes_on_a_miss():
    writers = {s.name for s in vd.steps("CUST-0001") if s.writes_on_miss}
    assert {"health", "formfill/templates", "help/search"} <= writers
