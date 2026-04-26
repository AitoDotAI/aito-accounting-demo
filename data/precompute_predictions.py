#!/usr/bin/env python3
"""Pre-compute all predictions for the Predictive Ledger demo.

Multi-tenant: writes one subdir per customer at
data/precomputed/{customer_id}/{name}.json. The API serves these
files directly — no runtime Aito calls except for interactive Form
Fill.

Usage:
    ./do load-data                                              # upload to Aito first
    python data/precompute_predictions.py                       # all customers
    python data/precompute_predictions.py --customers CUST-0000 # just one
    python data/precompute_predictions.py --limit 5             # first 5 customers
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_client import AitoClient, AitoError  # noqa: E402
from src.config import load_config  # noqa: E402
from src.invoice_service import predict_invoice  # noqa: E402
from src.matching_service import match_all  # noqa: E402
from src.rulemining_service import mine_rules  # noqa: E402
from src.anomaly_service import scan_all  # noqa: E402
from src.quality_service import (  # noqa: E402
    compute_prediction_quality,
    compute_rule_performance,
    get_quality_overview,
    mine_rules_for_customer,
)

random.seed(42)

DATA_DIR = Path(__file__).parent
PRECOMPUTED_DIR = DATA_DIR / "precomputed"


def load_fixture(name: str) -> list[dict]:
    with open(DATA_DIR / f"{name}.json") as f:
        return json.load(f)


def save(customer_id: str, name: str, data: dict) -> int:
    """Write data/precomputed/{customer_id}/{name}.json. Returns size in bytes."""
    out_dir = PRECOMPUTED_DIR / customer_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    return path.stat().st_size


def precompute_invoices_pending(
    client: AitoClient, customer_id: str, invoices: list[dict], rules: list[dict]
) -> dict:
    """Predict GL + approver for all unrouted invoices for the customer.

    Mirrors the /api/invoices/pending endpoint shape: invoices[] +
    metrics{}.
    """
    unrouted = [inv for inv in invoices if not inv.get("routed")]
    sample = unrouted[:50] if len(unrouted) >= 50 else unrouted
    if not sample:
        sample = invoices[:50]

    with ThreadPoolExecutor(max_workers=8) as pool:
        predictions = list(
            pool.map(
                lambda inv: predict_invoice(
                    client, {**inv, "customer_id": customer_id}, rules=rules
                ),
                sample,
            )
        )

    total = len(predictions)
    rule_n = sum(1 for p in predictions if p.source == "rule")
    aito_n = sum(1 for p in predictions if p.source == "aito")
    review_n = sum(1 for p in predictions if p.source == "review")
    confs = [p.confidence for p in predictions if p.confidence > 0]
    metrics = {
        "automation_rate": round((rule_n + aito_n) / total, 2) if total else 0,
        "avg_confidence": round(sum(confs) / len(confs), 2) if confs else 0,
        "total": total,
        "rule_count": rule_n,
        "aito_count": aito_n,
        "review_count": review_n,
    }
    return {"invoices": [p.to_dict() for p in predictions], "metrics": metrics}


def precompute_matching(client: AitoClient, customer_id: str) -> dict:
    return match_all(client, customer_id=customer_id)


def precompute_rules(client: AitoClient, customer_id: str) -> dict:
    return mine_rules(client, customer_id=customer_id)


def precompute_anomalies(client: AitoClient, customer_id: str) -> dict:
    return scan_all(client, customer_id=customer_id)


def precompute_quality_overview(client: AitoClient, customer_id: str) -> dict:
    return get_quality_overview(client, customer_id=customer_id)


def precompute_prediction_accuracy(client: AitoClient, customer_id: str) -> dict:
    """Real GL accuracy via Aito _evaluate + rules-only baseline.

    Delegates to the same service function the live endpoint uses, so
    the precomputed JSON is byte-identical to a warm cache hit.
    """
    return compute_prediction_quality(client, customer_id=customer_id)


def precompute_rule_performance_for_customer(client: AitoClient, customer_id: str) -> dict:
    """Mine per-customer rules and replay them — same shape as the
    /api/quality/rules endpoint."""
    return compute_rule_performance(client, customer_id=customer_id)


def precompute_one_customer(
    client: AitoClient,
    customer_id: str,
    invoices_for_customer: list[dict],
) -> dict[str, int]:
    """Run all precomputes for a single customer, return {name: bytes_written}."""
    sizes: dict[str, int] = {}

    # Rules are reused across the invoice/accuracy precomputes
    mined_rules = mine_rules_for_customer(client, customer_id)

    sizes["invoices_pending"] = save(
        customer_id, "invoices_pending",
        precompute_invoices_pending(client, customer_id, invoices_for_customer, mined_rules),
    )
    sizes["matching_pairs"] = save(
        customer_id, "matching_pairs", precompute_matching(client, customer_id),
    )
    sizes["rules_candidates"] = save(
        customer_id, "rules_candidates", precompute_rules(client, customer_id),
    )
    sizes["anomalies_scan"] = save(
        customer_id, "anomalies_scan", precompute_anomalies(client, customer_id),
    )
    sizes["quality_overview"] = save(
        customer_id, "quality_overview", precompute_quality_overview(client, customer_id),
    )
    sizes["prediction_accuracy"] = save(
        customer_id, "prediction_accuracy",
        precompute_prediction_accuracy(client, customer_id),
    )
    sizes["rule_performance"] = save(
        customer_id, "rule_performance",
        precompute_rule_performance_for_customer(client, customer_id),
    )
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", help="Comma-separated customer ids to process")
    parser.add_argument("--limit", type=int, help="Process only the first N customers")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel customers (1=sequential, 4=good for 256 customers; watch Aito QPS)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip customers that already have all 7 precomputed JSON files",
    )
    args = parser.parse_args()

    config = load_config()
    client = AitoClient(config)

    if not client.check_connectivity():
        print("Error: Cannot connect to Aito. Run ./do load-data first.", file=sys.stderr)
        sys.exit(1)

    customers = load_fixture("customers")
    if args.customers:
        wanted = set(args.customers.split(","))
        customers = [c for c in customers if c["customer_id"] in wanted]
    if args.limit:
        customers = customers[: args.limit]

    all_invoices = load_fixture("invoices")
    by_customer: dict[str, list[dict]] = {}
    for inv in all_invoices:
        by_customer.setdefault(inv["customer_id"], []).append(inv)

    PRECOMPUTED_DIR.mkdir(exist_ok=True)
    expected_files = {
        "invoices_pending.json", "matching_pairs.json", "rules_candidates.json",
        "anomalies_scan.json", "quality_overview.json",
        "prediction_accuracy.json", "rule_performance.json",
    }

    if args.skip_existing:
        before = len(customers)
        customers = [
            c for c in customers
            if not (PRECOMPUTED_DIR / c["customer_id"]).is_dir()
            or set((PRECOMPUTED_DIR / c["customer_id"]).iterdir()) and
               not expected_files.issubset({p.name for p in (PRECOMPUTED_DIR / c["customer_id"]).iterdir()})
        ]
        print(f"Skip existing: {before - len(customers)} done, {len(customers)} remaining")

    print(f"Precomputing for {len(customers)} customer(s) with workers={args.workers}...")

    total_bytes = 0
    t0 = time.time()
    completed = 0

    def run_one(idx_customer: tuple[int, dict]) -> tuple[int, str, dict, int, float]:
        idx, customer = idx_customer
        cid = customer["customer_id"]
        invs = by_customer.get(cid, [])
        t_cust = time.time()
        try:
            sizes = precompute_one_customer(client, cid, invs)
            return idx, cid, sizes, len(invs), time.time() - t_cust
        except Exception as e:
            print(f"  [{idx}/{len(customers)}] {cid}: ERROR {e}", file=sys.stderr)
            return idx, cid, {}, len(invs), time.time() - t_cust

    if args.workers <= 1:
        for i, customer in enumerate(customers, 1):
            idx, cid, sizes, n_inv, elapsed = run_one((i, customer))
            kb = sum(sizes.values()) / 1024
            total_bytes += sum(sizes.values())
            completed += 1
            print(
                f"  [{idx}/{len(customers)}] {cid} "
                f"({customer['size_tier']}, {n_inv} inv): {kb:.0f} KB in {elapsed:.1f}s",
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for idx, cid, sizes, n_inv, elapsed in pool.map(
                run_one, list(enumerate(customers, 1))
            ):
                kb = sum(sizes.values()) / 1024
                total_bytes += sum(sizes.values())
                completed += 1
                print(
                    f"  [{idx}/{len(customers)}] {cid} ({n_inv} inv): "
                    f"{kb:.0f} KB in {elapsed:.1f}s",
                    flush=True,
                )

    total_elapsed = time.time() - t0
    print(
        f"\nDone. {total_bytes / 1024:.0f} KB across {completed} customers "
        f"in {total_elapsed:.0f}s ({total_elapsed / max(1, completed):.1f}s/customer)."
    )
    print(f"Output: {PRECOMPUTED_DIR}/")


if __name__ == "__main__":
    main()
