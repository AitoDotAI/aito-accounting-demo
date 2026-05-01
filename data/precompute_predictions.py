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


EMPTY_RULES_CANDIDATES = {
    "candidates": [],
    "metrics": {"total": 0, "high_precision": 0, "medium_precision": 0, "promoted": 0},
}
EMPTY_RULE_PERFORMANCE = {"rules": []}
EMPTY_PREDICTION_ACCURACY = {
    "overall_accuracy": 0, "gl_accuracy": 0, "approver_accuracy": 0,
    "high_conf_accuracy": 0, "override_rate": 0, "dangerous_errors": 0,
    "base_accuracy": 0, "rules_coverage": 0, "rules_accuracy_within": 0,
    "rules_total_accuracy": 0, "geom_mean_p": 0,
    "confidence_table": [], "accuracy_by_type": [], "total_evaluated": 0,
}
EMPTY_MATCHING = {
    "pairs": [],
    "metrics": {"matched": 0, "suggested": 0, "unmatched": 0, "total": 0,
                "avg_confidence": 0, "match_rate": 0},
}
EMPTY_ANOMALIES = {
    "flags": [],
    "metrics": {"total": 0, "high": 0, "medium": 0, "low": 0, "scanned": 0},
}
EMPTY_QUALITY_OVERVIEW = {
    "automation": {"total": 0, "rule": 0, "aito": 0, "human": 0, "none": 0,
                   "rule_pct": 0, "aito_pct": 0, "human_pct": 0, "automation_rate": 0},
    "overrides": {"total": 0, "by_field": {}, "rate_pct": 0},
    "override_patterns": [],
}


def precompute_one_customer(
    client: AitoClient,
    customer_id: str,
    invoices_for_customer: list[dict],
    lite: bool = False,
) -> dict[str, int]:
    """Run all precomputes for a single customer, return {name: bytes_written}.

    `lite=True` skips per-vendor rule mining, _evaluate-based accuracy,
    and rule replay -- writing empty JSON for those views. Use it for
    small/midmarket tier customers where the demo persona is "just
    signed up, no patterns yet" and the slow Aito calls would just
    produce noisy stats.
    """
    sizes: dict[str, int] = {}

    if lite:
        mined_rules: list[dict] = []
    else:
        # Rules are reused across the invoice/accuracy precomputes
        mined_rules = mine_rules_for_customer(client, customer_id)

    # Predictions are the headline feature — done for everyone.
    sizes["invoices_pending"] = save(
        customer_id, "invoices_pending",
        precompute_invoices_pending(client, customer_id, invoices_for_customer, mined_rules),
    )

    if lite:
        # "Just signed up" persona: predictions only, empty everything else.
        # All views render realistic empty states for these.
        sizes["matching_pairs"] = save(customer_id, "matching_pairs", EMPTY_MATCHING)
        sizes["anomalies_scan"] = save(customer_id, "anomalies_scan", EMPTY_ANOMALIES)
        sizes["quality_overview"] = save(customer_id, "quality_overview", EMPTY_QUALITY_OVERVIEW)
        sizes["rules_candidates"] = save(customer_id, "rules_candidates", EMPTY_RULES_CANDIDATES)
        sizes["prediction_accuracy"] = save(customer_id, "prediction_accuracy", EMPTY_PREDICTION_ACCURACY)
        sizes["rule_performance"] = save(customer_id, "rule_performance", EMPTY_RULE_PERFORMANCE)
    else:
        sizes["matching_pairs"] = save(
            customer_id, "matching_pairs", precompute_matching(client, customer_id),
        )
        sizes["anomalies_scan"] = save(
            customer_id, "anomalies_scan", precompute_anomalies(client, customer_id),
        )
        sizes["quality_overview"] = save(
            customer_id, "quality_overview", precompute_quality_overview(client, customer_id),
        )
        sizes["rules_candidates"] = save(
            customer_id, "rules_candidates", precompute_rules(client, customer_id),
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


def precompute_help_related(
    client: AitoClient,
    customer_ids: list[str] | None = None,
) -> int:
    """Precompute the 'users who read this also read' lookups.

    Cold-path `_recommend` against help_impressions takes 5–12 s
    against a fresh Aito instance — bad enough that the first click
    on any expanded help article looks broken. Result is small
    (~1 KB per (customer, article) pair) and stable for hours, so
    we ship it as a static JSON and let the live endpoint fall back
    when it's missing.

    By default we cover the demo's most-visited customers:
    CUST-0000 + the four next-largest. Other tenants take the cold
    hit on first use, then the in-process cache covers reuse.
    """
    from src.help_service import related_articles, _eligibility_clause  # noqa: F401

    articles = load_fixture("help_articles")
    by_customer: dict[str, list[str]] = {"*": []}
    for a in articles:
        by_customer.setdefault(a.get("customer_id"), []).append(a["article_id"])

    if customer_ids is None:
        customers = sorted(load_fixture("customers"), key=lambda c: -c.get("invoice_count", 0))
        customer_ids = [c["customer_id"] for c in customers[:5]]

    out: dict[str, dict[str, list[dict]]] = {}
    jobs: list[tuple[str, str]] = []
    for cid in customer_ids:
        # Visible to this customer = global ('*') + own internal
        visible = (by_customer.get("*", []) + by_customer.get(cid, []))
        for art in visible:
            jobs.append((cid, art))

    print(f"  help_related: {len(customer_ids)} customers × visible articles = {len(jobs)} entries")

    def fetch(job: tuple[str, str]) -> tuple[str, str, list[dict]]:
        cid, art = job
        try:
            return cid, art, related_articles(client, art, cid, limit=4)
        except Exception:
            return cid, art, []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for cid, art, rel in pool.map(fetch, jobs):
            out.setdefault(cid, {})[art] = rel

    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PRECOMPUTED_DIR / "help_related.json"
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    return out_path.stat().st_size


def precompute_landing(client: AitoClient, vendor_limit: int = 8, tenants_per_vendor: int = 4) -> int:
    """Precompute the home page payload.

    Without this, the home screen does shared_vendors + 4 parallel
    formfill/template calls per vendor on first paint — visibly slow
    on cold deploys. Producing landing.json reduces that to one
    static-file read.
    """
    from src.multitenancy_service import compute_shared_vendors
    from src.formfill_service import predict_template

    vendors = compute_shared_vendors()[:vendor_limit]
    templates: dict[str, dict] = {}

    def fetch(vendor: str, customer_id: str) -> tuple[str, dict | None]:
        try:
            tpl = predict_template(client, customer_id, vendor)
        except AitoError as e:
            print(f"  landing template skipped {customer_id}/{vendor}: {e}")
            tpl = None
        return f"{vendor}|{customer_id}", tpl

    jobs: list[tuple[str, str]] = []
    for v in vendors:
        for t in v["tenants"][:tenants_per_vendor]:
            jobs.append((v["vendor"], t["customer_id"]))

    print(f"  landing: {len(vendors)} vendors × up to {tenants_per_vendor} tenants = {len(jobs)} templates")
    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, tpl in pool.map(lambda j: fetch(*j), jobs):
            if tpl is not None:
                templates[key] = tpl

    payload = {"vendors": vendors, "templates": templates}
    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PRECOMPUTED_DIR / "landing.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    return out_path.stat().st_size


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
    parser.add_argument(
        "--lite-threshold", type=int, default=0,
        help="Customers with fewer invoices than this get the lite "
             "precompute (no rule mining, no _evaluate, empty rule replay). "
             "Default 0 = full precompute for everyone.",
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

    # Landing page payload + help_related — both run once per
    # instance, not per-customer. Skipped when --customers narrows
    # the run since the user is iterating on a single tenant.
    if not args.customers and not args.skip_existing:
        try:
            landing_bytes = precompute_landing(client)
            print(f"  landing.json: {landing_bytes / 1024:.1f} KB")
        except Exception as e:
            print(f"  landing precompute error: {e}", file=sys.stderr)
        try:
            help_bytes = precompute_help_related(client)
            print(f"  help_related.json: {help_bytes / 1024:.1f} KB")
        except Exception as e:
            print(f"  help_related precompute error: {e}", file=sys.stderr)

    total_bytes = 0
    t0 = time.time()
    completed = 0

    def run_one(idx_customer: tuple[int, dict]) -> tuple[int, str, dict, int, float, bool]:
        idx, customer = idx_customer
        cid = customer["customer_id"]
        invs = by_customer.get(cid, [])
        lite = args.lite_threshold > 0 and len(invs) < args.lite_threshold
        t_cust = time.time()
        try:
            sizes = precompute_one_customer(client, cid, invs, lite=lite)
            return idx, cid, sizes, len(invs), time.time() - t_cust, lite
        except Exception as e:
            print(f"  [{idx}/{len(customers)}] {cid}: ERROR {e}", file=sys.stderr)
            return idx, cid, {}, len(invs), time.time() - t_cust, lite

    def _print_row(idx: int, cid: str, n_inv: int, kb: float, elapsed: float, lite: bool, tier: str = "") -> None:
        suffix = " [lite]" if lite else ""
        tier_str = f" ({tier}, {n_inv} inv)" if tier else f" ({n_inv} inv)"
        print(
            f"  [{idx}/{len(customers)}] {cid}{tier_str}: "
            f"{kb:.0f} KB in {elapsed:.1f}s{suffix}",
            flush=True,
        )

    if args.workers <= 1:
        for i, customer in enumerate(customers, 1):
            idx, cid, sizes, n_inv, elapsed, lite = run_one((i, customer))
            kb = sum(sizes.values()) / 1024
            total_bytes += sum(sizes.values())
            completed += 1
            _print_row(idx, cid, n_inv, kb, elapsed, lite, customer["size_tier"])
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for idx, cid, sizes, n_inv, elapsed, lite in pool.map(
                run_one, list(enumerate(customers, 1))
            ):
                kb = sum(sizes.values()) / 1024
                total_bytes += sum(sizes.values())
                completed += 1
                _print_row(idx, cid, n_inv, kb, elapsed, lite)

    total_elapsed = time.time() - t0
    print(
        f"\nDone. {total_bytes / 1024:.0f} KB across {completed} customers "
        f"in {total_elapsed:.0f}s ({total_elapsed / max(1, completed):.1f}s/customer)."
    )
    print(f"Output: {PRECOMPUTED_DIR}/")


if __name__ == "__main__":
    main()
