"""Per-customer precompute reads.

`src.precomputed` is a thin wrapper over `src.precompute_store`
that namespaces keys per customer (`cust:{customer_id}:{name}`).
Reads fall through L1 → Aito → bootstrap JSON.

These tests pin the wrapper's contract so endpoint code that calls
`precomputed.load(customer_id, name)` keeps working.
"""

import json
from pathlib import Path

from src import precomputed, precompute_store


def _patch_store(tmp_path, monkeypatch):
    """Detach the store from any real Aito client and point its
    bootstrap-file lookup at a tmp dir."""
    monkeypatch.setattr(precompute_store, "_aito", None)
    monkeypatch.setattr(precompute_store, "_FALLBACK_DIR", tmp_path)
    precompute_store.invalidate()


def test_load_returns_none_when_file_missing(tmp_path, monkeypatch):
    _patch_store(tmp_path, monkeypatch)
    assert precomputed.load("CUST-NEVER", "invoices_pending") is None


def test_has_returns_false_when_file_missing(tmp_path, monkeypatch):
    _patch_store(tmp_path, monkeypatch)
    assert precomputed.has("CUST-NEVER", "invoices_pending") is False


def test_load_returns_parsed_json_when_file_exists(tmp_path, monkeypatch):
    _patch_store(tmp_path, monkeypatch)
    cust_dir = tmp_path / "CUST-0000"
    cust_dir.mkdir()
    payload = {"invoices": [{"invoice_id": "I1"}], "metrics": {"total": 1}}
    (cust_dir / "invoices_pending.json").write_text(json.dumps(payload))

    assert precomputed.load("CUST-0000", "invoices_pending") == payload
    assert precomputed.has("CUST-0000", "invoices_pending") is True


def test_per_customer_key_format():
    """Pin the namespace shape — `cust:{id}:{name}`. Endpoint
    code never builds these by hand, but the precompute script
    and the store share the convention."""
    assert precompute_store.per_customer_key("CUST-0000", "invoices_pending") \
        == "cust:CUST-0000:invoices_pending"


def test_layout_matches_expected_filenames():
    """The endpoint code expects these exact names per customer."""
    expected = {
        "invoices_pending",
        "matching_pairs",
        "rules_candidates",
        "anomalies_scan",
        "quality_overview",
        "prediction_accuracy",
        "rule_performance",
    }
    app_src = (Path(__file__).resolve().parent.parent / "src" / "app.py").read_text()
    for name in expected:
        assert f'precomputed.load(customer_id, "{name}")' in app_src, (
            f"Endpoint for {name!r} doesn't load precomputed file"
        )
