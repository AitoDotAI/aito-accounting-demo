#!/usr/bin/env python3
"""Pre-compute all predictions for the Predictive Ledger demo.

Runs after data is loaded into Aito. Produces JSON files in
data/precomputed/ that the API serves directly — no runtime
Aito calls needed except for interactive Form Fill.

Usage:
    ./do load-data                          # upload data to Aito first
    python data/precompute_predictions.py   # then precompute
"""

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_client import AitoClient, AitoError
from src.config import load_config
from src.invoice_service import (
    GL_LABELS, predict_invoice, compute_metrics, check_rules,
    _extract_alternatives, _extract_why_factors,
)
from src.matching_service import match_bank_txn_to_invoice, _amount_match_score
from src.rulemining_service import mine_rules
from src.anomaly_service import scan_invoice
from src.quality_service import compute_override_stats, compute_override_patterns

random.seed(42)

DATA_DIR = Path(__file__).parent
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
PRECOMPUTED_DIR.mkdir(exist_ok=True)


def load_fixture(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def save_precomputed(name: str, data: dict) -> None:
    path = PRECOMPUTED_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=None, ensure_ascii=False)
    size_kb = path.stat().st_size / 1024
    print(f"  saved {name}.json ({size_kb:.0f} KB)")


def precompute_invoices(client: AitoClient, invoices: list[dict]) -> None:
    """Predict GL code + approver for a sample of pending invoices."""
    print("Precomputing invoice predictions...")

    # Pick 50 diverse invoices: mix of vendors, amounts, categories
    unrouted = [inv for inv in invoices if not inv["routed"]]
    routed = [inv for inv in invoices if inv["routed"]]
    sample = random.sample(unrouted, min(20, len(unrouted)))
    sample += random.sample(routed, min(30, len(routed)))

    predictions = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(predict_invoice, client, inv): inv for inv in sample}
        for future in futures:
            try:
                pred = future.result()
                predictions.append(pred.to_dict())
            except Exception as e:
                print(f"    error: {e}")

    metrics = compute_metrics([type('P', (), d)() for d in predictions])  # quick hack for dataclass
    # Recompute metrics properly
    total = len(predictions)
    rule_count = sum(1 for p in predictions if p["source"] == "rule")
    aito_count = sum(1 for p in predictions if p["source"] == "aito")
    review_count = sum(1 for p in predictions if p["source"] == "review")
    confs = [p["confidence"] for p in predictions if p["confidence"] > 0]
    metrics = {
        "automation_rate": round((rule_count + aito_count) / total, 2) if total else 0,
        "avg_confidence": round(sum(confs) / len(confs), 2) if confs else 0,
        "total": total,
        "rule_count": rule_count,
        "aito_count": aito_count,
        "review_count": review_count,
    }

    save_precomputed("invoices_pending", {"invoices": predictions, "metrics": metrics})


def precompute_matching(client: AitoClient, invoices: list[dict], bank_txns: list[dict]) -> None:
    """Match a sample of bank transactions to invoices."""
    print("Precomputing payment matching...")

    # Pick 20 matched bank transactions with diverse vendors
    matched_txns = [t for t in bank_txns if t.get("invoice_id")]
    unmatched_txns = [t for t in bank_txns if not t.get("invoice_id")]

    # Get a diverse set — normalize field names for matching service
    vendors_seen = set()
    sample_txns = []
    for txn in matched_txns:
        if txn["vendor_name"] not in vendors_seen and len(sample_txns) < 8:
            # Matching service expects txn_id, not transaction_id
            normalized = {
                "txn_id": txn.get("transaction_id", txn.get("txn_id")),
                "description": txn["description"],
                "amount": txn["amount"],
                "bank": txn.get("bank", ""),
            }
            sample_txns.append(normalized)
            vendors_seen.add(txn["vendor_name"])
    # Add a few unmatched
    for txn in random.sample(unmatched_txns, min(3, len(unmatched_txns))):
        sample_txns.append({
            "txn_id": txn.get("transaction_id", txn.get("txn_id")),
            "description": txn["description"],
            "amount": txn["amount"],
            "bank": txn.get("bank", ""),
        })

    # Build open invoices list from the matched invoice IDs
    inv_by_id = {inv["invoice_id"]: inv for inv in invoices}
    open_invoices = []
    for txn in sample_txns:
        if txn.get("invoice_id") and txn["invoice_id"] in inv_by_id:
            inv = inv_by_id[txn["invoice_id"]]
            open_invoices.append({
                "invoice_id": inv["invoice_id"],
                "vendor": inv["vendor"],
                "amount": inv["amount"],
            })

    # Add some invoices that won't match (for unmatched display)
    extra = random.sample(invoices, min(5, len(invoices)))
    for inv in extra:
        if inv["invoice_id"] not in {oi["invoice_id"] for oi in open_invoices}:
            open_invoices.append({
                "invoice_id": inv["invoice_id"],
                "vendor": inv["vendor"],
                "amount": inv["amount"],
            })

    pairs = []
    used_txns = set()
    remaining = list(open_invoices)

    for txn in sample_txns:
        pair = match_bank_txn_to_invoice(client, txn, remaining)
        if pair and pair.bank_txn_id:
            used_txns.add(pair.bank_txn_id)
            remaining = [inv for inv in remaining if inv["invoice_id"] != pair.invoice_id]
            pairs.append(pair.to_dict())
        else:
            pairs.append({
                "invoice_id": None,
                "invoice_vendor": None,
                "invoice_amount": None,
                "bank_txn_id": txn.get("txn_id"),
                "bank_description": txn["description"],
                "bank_amount": txn["amount"],
                "bank_name": txn.get("bank"),
                "confidence": 0.0,
                "status": "unmatched",
                "explanation": [],
            })

    matched = sum(1 for p in pairs if p["status"] == "matched")
    suggested = sum(1 for p in pairs if p["status"] == "suggested")
    unmatched = sum(1 for p in pairs if p["status"] == "unmatched")
    confs = [p["confidence"] for p in pairs if p["confidence"] > 0]

    save_precomputed("matching_pairs", {
        "pairs": pairs,
        "metrics": {
            "matched": matched,
            "suggested": suggested,
            "unmatched": unmatched,
            "total": len(pairs),
            "avg_confidence": round(sum(confs) / len(confs), 2) if confs else 0,
            "match_rate": round((matched + suggested) / len(pairs), 2) if pairs else 0,
        },
    })


def precompute_rules(client: AitoClient) -> None:
    """Mine rule candidates from the full dataset."""
    print("Precomputing rule mining...")
    result = mine_rules(client)
    save_precomputed("rules_candidates", result)


def precompute_anomalies(client: AitoClient, invoices: list[dict]) -> None:
    """Scan a sample for anomalies."""
    print("Precomputing anomaly detection...")

    # Mix of normal and potentially anomalous invoices
    sample = random.sample(invoices, min(30, len(invoices)))
    # Add some with wrong GL codes (synthetic anomalies)
    for inv in random.sample(invoices, min(5, len(invoices))):
        anomalous = dict(inv)
        anomalous["gl_code"] = random.choice([c for c in GL_LABELS if c != inv["gl_code"]])
        anomalous["invoice_id"] = anomalous["invoice_id"] + "-A"
        sample.append(anomalous)

    flags = []
    for inv in sample:
        flag = scan_invoice(client, inv)
        if flag is not None:
            flags.append(flag.to_dict())

    flags.sort(key=lambda f: f["anomaly_score"], reverse=True)
    high = sum(1 for f in flags if f["severity"] == "high")
    medium = sum(1 for f in flags if f["severity"] == "medium")
    low = sum(1 for f in flags if f["severity"] == "low")

    save_precomputed("anomalies_scan", {
        "flags": flags,
        "metrics": {"total": len(flags), "high": high, "medium": medium, "low": low, "scanned": len(sample)},
    })


def precompute_quality(client: AitoClient, invoices: list[dict]) -> None:
    """Compute quality metrics from the full dataset."""
    print("Precomputing quality overview...")

    # Automation breakdown from fixture data (no Aito search limit issues)
    total = len(invoices)
    rule = sum(1 for inv in invoices if inv["routed_by"] == "rule")
    aito = sum(1 for inv in invoices if inv["routed_by"] == "aito")
    human = sum(1 for inv in invoices if inv["routed_by"] == "human")
    none_ = sum(1 for inv in invoices if inv["routed_by"] == "none")

    automation = {
        "total": total,
        "rule": rule, "aito": aito, "human": human, "none": none_,
        "rule_pct": round(rule / total * 100), "aito_pct": round(aito / total * 100),
        "human_pct": round(human / total * 100),
        "automation_rate": round((rule + aito) / total * 100),
    }

    overrides = compute_override_stats(client)
    override_patterns = compute_override_patterns(client)

    save_precomputed("quality_overview", {
        "automation": automation,
        "overrides": overrides,
        "override_patterns": override_patterns,
    })


def precompute_prediction_accuracy(client: AitoClient, invoices: list[dict]) -> None:
    """Compute real prediction accuracy by predicting on a sample and comparing to ground truth."""
    print("Precomputing prediction accuracy (200 sample)...")

    sample = random.sample(invoices, min(200, len(invoices)))

    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        def predict_and_compare(inv):
            try:
                pred = predict_invoice(client, inv)
                return {
                    "invoice_id": inv["invoice_id"],
                    "predicted_gl": pred.gl_code,
                    "actual_gl": inv["gl_code"],
                    "gl_confidence": pred.gl_confidence,
                    "correct_gl": pred.gl_code == inv["gl_code"],
                    "predicted_approver": pred.approver.replace("AP / ", "") if pred.approver else None,
                    "actual_approver": inv["approver"],
                    "approver_confidence": pred.approver_confidence,
                    "correct_approver": (pred.approver or "").replace("AP / ", "") == inv["approver"],
                    "source": pred.source,
                }
            except Exception:
                return None

        futures = list(pool.map(predict_and_compare, sample))
        results = [r for r in futures if r is not None]

    # Accuracy by type
    gl_correct = sum(1 for r in results if r["correct_gl"])
    approver_correct = sum(1 for r in results if r["correct_approver"])
    total = len(results)

    # Accuracy by confidence band
    bands = [
        ("0.95 – 1.00", 0.95, 1.01),
        ("0.85 – 0.95", 0.85, 0.95),
        ("0.70 – 0.85", 0.70, 0.85),
        ("0.50 – 0.70", 0.50, 0.70),
        ("< 0.50", 0.0, 0.50),
    ]
    conf_table = []
    for label, lo, hi in bands:
        band_results = [r for r in results if lo <= r["gl_confidence"] < hi]
        band_correct = sum(1 for r in band_results if r["correct_gl"])
        n = len(band_results)
        conf_table.append({
            "range": label,
            "volume": f"{n / total * 100:.0f}%" if total else "0%",
            "accuracy": round(band_correct / n * 100, 1) if n else 0,
            "count": n,
        })

    # Dangerous errors: high confidence but wrong
    high_conf_wrong = sum(1 for r in results if r["gl_confidence"] >= 0.85 and not r["correct_gl"])

    save_precomputed("prediction_accuracy", {
        "overall_accuracy": round(gl_correct / total * 100, 1) if total else 0,
        "gl_accuracy": round(gl_correct / total * 100, 1) if total else 0,
        "approver_accuracy": round(approver_correct / total * 100, 1) if total else 0,
        "override_rate": round((total - gl_correct) / total * 100, 1) if total else 0,
        "dangerous_errors": round(high_conf_wrong / total * 100, 1) if total else 0,
        "high_conf_accuracy": round(
            sum(1 for r in results if r["gl_confidence"] >= 0.85 and r["correct_gl"]) /
            max(1, sum(1 for r in results if r["gl_confidence"] >= 0.85)) * 100, 1
        ),
        "confidence_table": conf_table,
        "accuracy_by_type": [
            {"label": "GL code", "value": round(gl_correct / total * 100) if total else 0},
            {"label": "Approver routing", "value": round(approver_correct / total * 100) if total else 0},
        ],
        "total_evaluated": total,
    })


def precompute_rule_performance(client: AitoClient, invoices: list[dict]) -> None:
    """Compute real rule performance by replaying rules against the dataset."""
    print("Precomputing rule performance...")

    from src.invoice_service import RULES

    rules_data = []
    for rule_def in RULES:
        matching = [inv for inv in invoices if rule_def["match"](inv)]
        total = len(matching)
        if total == 0:
            continue

        correct_gl = sum(1 for inv in matching if inv["gl_code"] == rule_def["gl_code"])
        correct_approver = sum(1 for inv in matching if inv["approver"] == rule_def["approver"])
        precision = round(correct_gl / total, 2) if total else 0
        coverage = round(total / len(invoices) * 100, 1)

        # Trend: check last quarter vs overall
        rules_data.append({
            "rule": rule_def["name"],
            "fires_on": f"GL {rule_def['gl_code']} ({GL_LABELS.get(rule_def['gl_code'], rule_def['gl_code'])}), {rule_def['approver']}",
            "coverage": f"{coverage}%",
            "precision": precision,
            "total_matches": total,
            "correct": correct_gl,
            "trend": "stable" if precision >= 0.95 else ("drifting" if precision >= 0.80 else "degrading"),
            "status": "Active" if precision >= 0.95 else ("Drifting" if precision >= 0.80 else "Stale"),
        })

    save_precomputed("rule_performance", {"rules": rules_data})


def main():
    config = load_config()
    client = AitoClient(config)

    if not client.check_connectivity():
        print("Error: Cannot connect to Aito. Run ./do load-data first.")
        sys.exit(1)

    invoices = load_fixture("invoices")
    bank_txns = load_fixture("bank_transactions")

    print(f"Precomputing predictions for {len(invoices)} invoices...\n")

    precompute_invoices(client, invoices)
    precompute_matching(client, invoices, bank_txns)
    precompute_rules(client)
    precompute_anomalies(client, invoices)
    precompute_quality(client, invoices)
    precompute_prediction_accuracy(client, invoices)
    precompute_rule_performance(client, invoices)

    print(f"\nDone. Precomputed data in {PRECOMPUTED_DIR}/")


if __name__ == "__main__":
    main()
