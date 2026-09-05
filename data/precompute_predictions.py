#!/usr/bin/env python3
"""Pre-compute all predictions for the Predictive Ledger demo.

Multi-tenant: writes one subdir per customer at
data/precomputed/{customer_id}/{name}.json. The API serves these
files directly — no runtime Aito calls except for interactive Form
Fill.

Runs against either API generation. `--v2` computes through the v2
client instead, and everything it writes is namespaced (Aito keys get a
`v2:` prefix, files land under data/precomputed/v2/) because a
projection is only valid for the generation that produced it — serving
a v1-derived number from a v2 deployment is a wrong answer that looks
completely well-formed. See src/precompute_store.py.

Usage:
    ./do load-data                                              # upload to Aito first
    python data/precompute_predictions.py                       # all customers
    python data/precompute_predictions.py --customers CUST-0000 # just one
    python data/precompute_predictions.py --limit 5             # first 5 customers
    python data/precompute_predictions.py --v2                  # against AITO_V2_ENV
"""

import argparse
import json
import os
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


def load_fixture(name: str) -> list[dict]:
    with open(DATA_DIR / f"{name}.json") as f:
        return json.load(f)


def save(customer_id: str, name: str, data: dict) -> int:
    """Write data/precomputed/{customer_id}/{name}.json AND push to the
    Aito precompute store. Returns local file size in bytes.

    Two writes intentionally:
    - Local JSON: bootstrap fallback for dev / brief Aito outages.
    - Aito store: source of truth for running containers; refreshes
      on every precompute run without rebuilding the docker image.
    """
    from src import precompute_store

    key = precompute_store.per_customer_key(customer_id, name)
    # Ask the store where its bootstrap file goes rather than building
    # the path here — under --v2 it is a different subtree, and two
    # places computing it independently is how they drift apart.
    path = precompute_store.bootstrap_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    try:
        precompute_store.put(key, data)
    except Exception as e:
        print(f"  {customer_id}/{name}: aito-store push skipped: {e}")
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
    skip_evaluate: bool = False,
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
        # _evaluate is the memory-heavy call on the Aito server side
        # — it loads test/train splits + computes per-row predictions
        # and is what tipped the 1 M-scale instance into 504s. We
        # only run it for the headline customer (CUST-0000) by
        # default; the long tail gets the empty stub. Override with
        # --include-evaluate-for-tail if you really want full numbers
        # everywhere and have a beefier instance.
        if skip_evaluate:
            sizes["prediction_accuracy"] = save(
                customer_id, "prediction_accuracy", EMPTY_PREDICTION_ACCURACY,
            )
            sizes["rule_performance"] = save(
                customer_id, "rule_performance", EMPTY_RULE_PERFORMANCE,
            )
        else:
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

    from src import precompute_store

    # No re-init here: main() already wired the store to the v1 client,
    # and re-initializing with `client` would rebind it to the v2 client
    # under --v2 — pointing precompute_entries writes at an env that
    # doesn't hold that table.
    out_path = precompute_store.bootstrap_path("help_related")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    try:
        precompute_store.put("help_related", out)
    except Exception as e:
        print(f"  help_related: aito-store push skipped: {e}")
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

    from src import precompute_store

    payload = {"vendors": vendors, "templates": templates}
    out_path = precompute_store.bootstrap_path("landing")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    # Also push to the Aito-backed precompute store so deployed
    # containers pick up the new payload without a docker rebuild.
    # (Store init happens once in main() — see the note in
    # precompute_help_related for why it must not be repeated here.)
    try:
        precompute_store.put("landing", payload)
    except Exception as e:
        print(f"  landing: aito-store push skipped: {e}")
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
    parser.add_argument(
        "--evaluate-for", default="CUST-0000",
        help="Comma-separated customer ids that get full _evaluate-based "
             "prediction_accuracy + rule_performance precompute. The "
             "_evaluate call is the memory-heavy server-side path that "
             "tipped 1 M-scale Aito into 504 storms; running it for every "
             "customer is what produced the 2-customer cliff. Default: only "
             "the headline tenant (CUST-0000). Pass an empty string to skip "
             "for everyone, or `all` to opt back into the slow behaviour.",
    )
    parser.add_argument(
        "--v2", action="store_true",
        help="Compute through the Aito v2 API in $AITO_V2_ENV instead of v1. "
             "Outputs are namespaced (v2: keys, data/precomputed/v2/), so this "
             "never overwrites the v1 bootstrap files checked into git.",
    )
    args = parser.parse_args()

    config = load_config()
    # The store always talks v1: `precompute_entries` is an ordinary
    # table on master, not part of a v2 env branch. Only the *query*
    # client changes with --v2. See src/precompute_store.py.
    store_client = AitoClient(config)
    if args.v2:
        # Same interpretation the app uses, so a cutover's final state
        # (AITO_V2_ENV=master, meaning v2 with no /env/ segment) computes
        # against the same place the app will read. Passing "master"
        # through as an env name would build /env/master/ and 400.
        from src.aito_v2_client import AitoV2Client, resolve_env

        use_v2, target = resolve_env(os.environ.get("AITO_V2_ENV"))
        if not use_v2:
            print("--v2 needs AITO_V2_ENV set (an env name, or 'master' for "
                  "v2 against master). Build an env with: ./do v2-build",
                  file=sys.stderr)
            sys.exit(2)
        client = AitoV2Client(config.aito_api_url, config.aito_api_key, env=target)
        print(f"Computing against Aito v2 — {target or 'master (unscoped)'}")
    else:
        client = store_client

    # Initialize the Aito-backed precompute store once. Every
    # precompute_one_customer / precompute_landing / precompute_help_related
    # call below will push outputs into precompute_entries via save() /
    # precompute_store.put().
    from src import precompute_store
    precompute_store.init(store_client)

    # The store reads AITO_V2_ENV at import to pick its key namespace, so
    # a --v2 run with the variable unset would compute v2 answers and file
    # them under the v1 keys. Refuse rather than corrupt the v1 store.
    if args.v2 and precompute_store.namespace() != "v2:":
        print("--v2 requires AITO_V2_ENV to be set in the environment before "
              "import, so the precompute store namespaces its keys.", file=sys.stderr)
        sys.exit(2)

    # Connectivity probe — degraded but not down is OK; the
    # per-customer retry loop below will absorb transient failures.
    # We only abort if we can't connect at all over multiple tries.
    connectivity_ok = False
    for attempt in range(3):
        if client.check_connectivity():
            connectivity_ok = True
            break
        wait = 30 * (attempt + 1)
        print(
            f"Aito connectivity probe failed (attempt {attempt + 1}/3); "
            f"sleeping {wait}s before retry...",
            file=sys.stderr,
        )
        time.sleep(wait)
        client._breaker_failures = 0
        client._breaker_open_until = 0.0
    if not connectivity_ok:
        print("Error: Cannot connect to Aito after 3 attempts. Run ./do load-data first.", file=sys.stderr)
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

    # The output root depends on the namespace, so ask the store for it:
    # a hard-coded data/precomputed would, under --v2, point at the v1
    # tree and make `--skip-existing` skip customers whose v2 precompute
    # has never been written.
    def customer_dir(customer_id: str):
        return precompute_store.bootstrap_path(
            precompute_store.per_customer_key(customer_id, "invoices_pending")).parent

    output_root = customer_dir("_probe").parent
    output_root.mkdir(parents=True, exist_ok=True)
    expected_files = {
        "invoices_pending.json", "matching_pairs.json", "rules_candidates.json",
        "anomalies_scan.json", "quality_overview.json",
        "prediction_accuracy.json", "rule_performance.json",
    }

    if args.skip_existing:
        before = len(customers)
        customers = [
            c for c in customers
            # An existing-but-incomplete directory is reprocessed, and so
            # is an empty one — the previous form treated an empty dir as
            # done and skipped it.
            if not customer_dir(c["customer_id"]).is_dir()
            or not expected_files.issubset(
                {p.name for p in customer_dir(c["customer_id"]).iterdir()})
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

    # Backoff-retry for transient Aito failures during heavy
    # precompute traffic.
    #
    # At 1 M-row scale, one customer's precompute fan-out
    # (mine_rules + match_all + scan_all + compute_prediction_quality
    # + compute_rule_performance) overloads shared.aito.ai enough to
    # produce 504s. The client's circuit breaker then opens, every
    # call for the next ~10 s fails fast with status_code=503, and
    # the rest of the precompute writes empty stubs.
    #
    # Retry strategy: on AitoError, sleep, reset the breaker, and
    # retry the whole customer. Three attempts with 60 / 120 / 240 s
    # backoff gives Aito ~7 min to recover. Idempotent — save()
    # overwrites the previous attempt's files and Aito-store rows.
    PRECOMPUTE_MAX_ATTEMPTS = 3
    PRECOMPUTE_BACKOFF = [60, 120, 240]

    # Allow `--evaluate-for=all` to opt back into running _evaluate
    # everywhere, otherwise restrict to the listed ids.
    if args.evaluate_for.strip().lower() == "all":
        evaluate_for_set: set[str] | None = None  # None = run for everyone
    else:
        evaluate_for_set = {c.strip() for c in args.evaluate_for.split(",") if c.strip()}

    def _attempt_once(idx: int, cid: str, invs: list[dict], lite: bool, skip_evaluate: bool) -> dict:
        # Reset the breaker to clear any sticky 503 from a previous
        # customer's failure.
        client._breaker_failures = 0
        client._breaker_open_until = 0.0
        return precompute_one_customer(client, cid, invs, lite=lite, skip_evaluate=skip_evaluate)

    def run_one(idx_customer: tuple[int, dict]) -> tuple[int, str, dict, int, float, bool]:
        idx, customer = idx_customer
        cid = customer["customer_id"]
        invs = by_customer.get(cid, [])
        lite = args.lite_threshold > 0 and len(invs) < args.lite_threshold
        skip_evaluate = evaluate_for_set is not None and cid not in evaluate_for_set
        t_cust = time.time()
        last_err: Exception | None = None
        for attempt in range(PRECOMPUTE_MAX_ATTEMPTS):
            try:
                sizes = _attempt_once(idx, cid, invs, lite, skip_evaluate)
                if attempt > 0:
                    print(f"  [{idx}/{len(customers)}] {cid}: succeeded on attempt {attempt + 1}", flush=True)
                return idx, cid, sizes, len(invs), time.time() - t_cust, lite
            except Exception as e:
                last_err = e
                if attempt + 1 < PRECOMPUTE_MAX_ATTEMPTS:
                    backoff = PRECOMPUTE_BACKOFF[attempt]
                    print(
                        f"  [{idx}/{len(customers)}] {cid}: attempt {attempt + 1} failed "
                        f"({type(e).__name__}: {e}); sleeping {backoff}s then retrying...",
                        file=sys.stderr, flush=True,
                    )
                    time.sleep(backoff)
        print(
            f"  [{idx}/{len(customers)}] {cid}: all {PRECOMPUTE_MAX_ATTEMPTS} attempts FAILED; "
            f"last error: {last_err}",
            file=sys.stderr, flush=True,
        )
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
    print(f"Output: {output_root}/")


if __name__ == "__main__":
    main()
