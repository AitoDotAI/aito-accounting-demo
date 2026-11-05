"""A precompute missing the fields its page reads is refused (td-20261030211357041898).

The symptom was a P2: "0 of 8 payments matched by Aito". Nothing was
wrong with the matcher -- `./do eval-matching` measures 25/25 on
CUST-0000 at 0.91 mean confidence against a 1.8% random baseline. The
page reads `metrics.matched_by_aito` (frontend/app/matching/page.tsx:148)
and labels each row from `pair.matched_by` (:206), and all 255 committed
data/precomputed/*/matching_pairs.json predate both fields. Since
/api/matching/pairs returns the precompute before it will compute
anything, a deploy serving those files shows nothing matched by Aito
while Aito is matching everything.

scripts/verify_demo.py:117 already names this exact case -- "A payload
without `matched_by` predates ADR 0026: the precompute has not been
rebuilt, and the page would lead with lookups again... stale precompute?
run ./do precompute-v2". It can only say so after the fact, from
outside, against a running demo. The loader can refuse the payload
instead, and fall through to the live path that is known to work.
"""

import json
from pathlib import Path

from src import precomputed

REPO = Path(__file__).resolve().parent.parent

CURRENT = {
    "pairs": [
        {"bank_txn_id": "T-1", "invoice_id": "I-1", "matched_by": "aito",
         "status": "matched", "confidence": 0.9},
        {"bank_txn_id": "T-2", "invoice_id": "I-2", "matched_by": "reference",
         "status": "matched", "confidence": 1.0},
    ],
    "metrics": {"matched": 2, "matched_by_aito": 1, "matched_by_reference": 1,
                "total": 2, "unmatched": 0, "suggested": 0},
}


def served(monkeypatch, payload):
    """Pretend the store holds `payload` for every key."""
    monkeypatch.setattr("src.precompute_store.get", lambda key: payload)


def test_a_current_precompute_is_served(monkeypatch):
    served(monkeypatch, CURRENT)
    assert precomputed.load("CUST-0000", "matching_pairs") == CURRENT


def test_a_payload_without_the_aito_count_is_refused(monkeypatch):
    stale = json.loads(json.dumps(CURRENT))
    del stale["metrics"]["matched_by_aito"]
    served(monkeypatch, stale)
    assert precomputed.load("CUST-0000", "matching_pairs") is None, \
        "the page would read matched_by_aito as '--' and the demo would look broken"


def test_a_payload_whose_rows_are_unlabelled_is_refused(monkeypatch):
    stale = json.loads(json.dumps(CURRENT))
    for pair in stale["pairs"]:
        del pair["matched_by"]
    served(monkeypatch, stale)
    assert precomputed.load("CUST-0000", "matching_pairs") is None, \
        "no row could say whether Aito or a reference number matched it"


def test_the_refusal_says_what_to_run(monkeypatch, capsys):
    stale = json.loads(json.dumps(CURRENT))
    del stale["metrics"]["matched_by_aito"]
    served(monkeypatch, stale)
    precomputed._warned.clear()
    precomputed.load("CUST-0000", "matching_pairs")
    out = capsys.readouterr().out
    assert "matching_pairs" in out and "CUST-0000" in out
    assert "precompute" in out, "a silent fall-through leaves nobody to tell"


def test_the_refusal_is_logged_once_per_key(monkeypatch, capsys):
    stale = json.loads(json.dumps(CURRENT))
    del stale["metrics"]["matched_by_aito"]
    served(monkeypatch, stale)
    precomputed._warned.clear()
    for _ in range(3):
        precomputed.load("CUST-0000", "matching_pairs")
    assert capsys.readouterr().out.count("CUST-0000") == 1, \
        "255 tenants on every request would bury the message in its own noise"


def test_a_precompute_with_no_declared_fields_is_passed_through(monkeypatch):
    payload = {"anything": 1}
    served(monkeypatch, payload)
    assert precomputed.load("CUST-0000", "invoices_pending") == payload


def test_nothing_in_the_store_is_still_nothing(monkeypatch):
    served(monkeypatch, None)
    assert precomputed.load("CUST-0000", "matching_pairs") is None


def test_a_real_captured_payload_is_refused(monkeypatch):
    """Not a hand-built shape: four pairs and the metrics block as
    `./do precompute-v2` actually wrote them for CUST-0000 before ADR
    0026, captured into tests/fixtures/ so this runs on a clean checkout.

    The first version of this test read
    data/precomputed/CUST-0000/matching_pairs.json directly, which
    .gitignore excludes (only landing.json and help_related.json are
    tracked). It passed here and failed anywhere the generator had not
    been run -- the test asserted the state of my working copy.
    """
    path = REPO / "tests" / "fixtures" / "stale_matching_pairs.json"
    served(monkeypatch, json.loads(path.read_text()))
    precomputed._warned.clear()
    assert precomputed.load("CUST-0000", "matching_pairs") is None, \
        f"{path.name} predates matched_by and would show 0 matched by Aito"


# ── The writer's own payloads must be served ────────────────────────────
#
# CPO review of #66: EMPTY_MATCHING, which `--lite-threshold` writes for
# every small tenant, had no `matched_by_aito`, so the guard refused the
# precompute's own output on every request, permanently.

def test_a_genuinely_empty_ledger_with_the_current_metrics_is_served(monkeypatch):
    empty = {"pairs": [], "metrics": {"matched": 0, "suggested": 0, "unmatched": 0,
                                      "matched_by_reference": 0, "matched_by_aito": 0,
                                      "total": 0, "avg_confidence": 0, "match_rate": 0}}
    served(monkeypatch, empty)
    assert precomputed.load("CUST-0000", "matching_pairs") == empty


def test_the_precompute_writers_own_empty_matching_payload_is_served(monkeypatch):
    import importlib

    writer = importlib.import_module("data.precompute_predictions")
    served(monkeypatch, writer.EMPTY_MATCHING)
    assert precomputed.load("CUST-0000", "matching_pairs") == writer.EMPTY_MATCHING, \
        "the guard refuses what the lite-threshold path writes"
