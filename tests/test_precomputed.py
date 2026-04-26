"""Precomputed JSON loading.

The precompute pipeline writes per-customer JSON to
data/precomputed/{customer_id}/{name}.json. Endpoints serve these
files directly when present and fall back to live Aito otherwise.
This test fixes the file-layout contract so a precompute refactor
can't silently break the read path.
"""

import json
from pathlib import Path

from src import precomputed


def test_load_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(precomputed, "_DATA_DIR", tmp_path)
    assert precomputed.load("CUST-NEVER", "invoices_pending") is None


def test_has_returns_false_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(precomputed, "_DATA_DIR", tmp_path)
    assert precomputed.has("CUST-NEVER", "invoices_pending") is False


def test_load_returns_parsed_json_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(precomputed, "_DATA_DIR", tmp_path)
    cust_dir = tmp_path / "CUST-0000"
    cust_dir.mkdir()
    payload = {"invoices": [{"invoice_id": "I1"}], "metrics": {"total": 1}}
    (cust_dir / "invoices_pending.json").write_text(json.dumps(payload))

    assert precomputed.load("CUST-0000", "invoices_pending") == payload
    assert precomputed.has("CUST-0000", "invoices_pending") is True


def test_layout_matches_expected_filenames():
    """The endpoint code expects these exact filenames per customer."""
    expected = {
        "invoices_pending",
        "matching_pairs",
        "rules_candidates",
        "anomalies_scan",
        "quality_overview",
        "prediction_accuracy",
        "rule_performance",
    }
    # Read the names hard-coded in app.py to detect drift.
    app_src = (Path(__file__).resolve().parent.parent / "src" / "app.py").read_text()
    for name in expected:
        assert f'precomputed.load(customer_id, "{name}")' in app_src, (
            f"Endpoint for {name!r} doesn't load precomputed file"
        )
