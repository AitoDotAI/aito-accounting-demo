#!/usr/bin/env python3
"""Walk the canonical demo path against a running server and check each step.

    ./do dev            # in one terminal
    ./do verify-demo    # in another

`./do aito-check` asserts that Aito answers correctly. This asserts that
the *demo* works: the same endpoints, in the same order, that
`docs/demo-script.md` walks a viewer through — and that each one returns
content worth showing, not an empty shell.

The distinction matters because the demo can break without any Aito query
breaking. A precompute key that doesn't match what the read path looks
for, a cache prefix missed under v2, a view that technically returns 200
with an empty list — all of those render as a blank panel mid-demo while
every underlying query is fine.

Each step therefore asserts on content, and reports its latency, because
"correct but takes 90 seconds" also fails a live demo. Steps are checked
in demo order so the first failure is the first thing a viewer would see.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE = "http://localhost:8200"
DEFAULT_CUSTOMER = "CUST-0000"

# A step slower than this still passes, but is called out: past this
# point a live audience reads the view as broken rather than loading.
SLOW_SECONDS = 5.0


@dataclass
class Step:
    """One stop on the demo path.

    `check` receives the decoded JSON body and returns a summary string,
    or raises AssertionError with what was wrong.
    """
    name: str
    path: str
    check: Any
    params: dict | None = None


def _hits(body: dict, *keys: str) -> list:
    """First non-empty list found under any of `keys`."""
    for key in keys:
        value = body.get(key)
        if isinstance(value, list) and value:
            return value
    return []


# ── Demo steps, in the order docs/demo-script.md presents them ───────


def check_health(body: dict) -> str:
    assert body.get("status") == "ok", f"health status is {body.get('status')!r}"
    assert body.get("aito_connected") is True, "server cannot reach Aito"
    return "server up, Aito reachable"


def check_customers(body: dict) -> str:
    customers = _hits(body, "customers")
    assert customers, "no customers — the tenant switcher would be empty"
    assert any(c.get("customer_id") == DEFAULT_CUSTOMER for c in customers), \
        f"{DEFAULT_CUSTOMER} missing from the customer list"
    return f"{len(customers)} tenants"


def check_invoices_pending(body: dict) -> str:
    """Step 1 — the inbox. Predictions, confidences, and the touchless rate."""
    invoices = _hits(body, "invoices", "pending", "items")
    assert invoices, "no pending invoices — the demo's opening view would be empty"

    predicted = [i for i in invoices if i.get("predicted_gl_code") or i.get("gl_code")]
    assert predicted, f"none of {len(invoices)} pending invoices carries a prediction"

    confidences = [i.get("confidence") for i in invoices if i.get("confidence") is not None]
    assert confidences, "no confidence values — the whole automation story is unshown"
    for confidence in confidences:
        assert 0.0 <= float(confidence) <= 1.0, f"confidence out of [0,1]: {confidence}"
    return f"{len(invoices)} pending, {len(predicted)} predicted"


def check_formfill_templates(body: dict) -> str:
    """Step 2 — smart form fill. Vendor quick-start templates."""
    templates = _hits(body, "templates", "vendors")
    assert templates, "no form-fill templates — the quick-start row would be empty"
    return f"{len(templates)} templates"


def check_rule_candidates(body: dict) -> str:
    """Step 6 — rule mining. Mined conjunctions with real support."""
    candidates = _hits(body, "candidates", "rules")
    assert candidates, "no rule candidates — the mining view would be empty"

    with_support = [c for c in candidates if c.get("support_total")]
    assert with_support, "every candidate has zero support — the exact-count stage is broken"
    return f"{len(candidates)} candidates, {len(with_support)} with support"


def check_matching_pairs(body: dict) -> str:
    """Step 4 — payment matching."""
    pairs = _hits(body, "pairs")
    assert pairs, "no matching pairs"
    matched = [p for p in pairs if p.get("status") != "unmatched"]
    assert matched, f"all {len(pairs)} transactions unmatched"
    return f"{len(matched)} matched / {len(pairs)}"


def check_anomalies(body: dict) -> str:
    """Step 5 — anomaly detection.

    Finding zero anomalies is a legitimate result, so this asserts the
    scan *ran*, and that anything it did flag carries the description
    and recommendation the card renders.
    """
    scanned = body.get("metrics", {}).get("scanned")
    assert scanned, f"anomaly scan reports nothing scanned: {scanned!r}"

    flags = _hits(body, "flags")
    for flag in flags:
        assert flag.get("description"), f"flagged invoice has nothing to show: {flag}"
        assert flag.get("recommendation"), f"flag has no recommended action: {flag}"
    return f"{scanned} scanned, {len(flags)} flagged"


def check_quality_overview(body: dict) -> str:
    """Step 7 — the automation split that opens the quality dashboard.

    The four shares are what the donut renders, so they have to be
    present, in range, and add up to the population they describe.
    """
    automation = body.get("automation", {})
    assert automation, f"quality overview has no automation split: {sorted(body)}"

    total = automation.get("total")
    assert total, f"automation split covers no invoices: {total!r}"
    parts = {k: automation.get(k) for k in ("rule", "aito", "human", "none")}
    for name, count in parts.items():
        assert isinstance(count, int), f"automation.{name} is not a count: {count!r}"
    assert sum(parts.values()) == total, \
        f"automation parts {parts} do not sum to total {total}"

    for key in ("rule_pct", "aito_pct", "human_pct", "automation_rate"):
        value = automation.get(key)
        assert value is not None, f"automation.{key} missing"
        assert 0 <= value <= 100, f"automation.{key} out of range: {value}"
    return (f"{automation['automation_rate']}% automated "
            f"({automation['aito_pct']}% Aito, {automation['rule_pct']}% rules)")


def check_quality_predictions(body: dict) -> str:
    """Step 7 — measured accuracy against the baseline it must beat.

    This endpoint reports percentages (98.0), not probabilities.
    Beating the baseline is the whole claim being demonstrated, so an
    accuracy that doesn't is a failure even though every call succeeded.
    """
    accuracy = body.get("overall_accuracy")
    baseline = body.get("base_accuracy")
    evaluated = body.get("total_evaluated")

    assert accuracy is not None, f"no accuracy reported: {sorted(body)}"
    assert evaluated, f"nothing was evaluated: {evaluated!r}"
    for name, value in (("overall_accuracy", accuracy), ("base_accuracy", baseline)):
        assert value is not None, f"{name} missing"
        assert 0 <= value <= 100, f"{name} is not a percentage: {value}"
    assert accuracy > baseline, \
        f"accuracy {accuracy}% does not beat the baseline {baseline}% — nothing to demo"

    assert _hits(body, "confidence_table"), "no confidence breakdown to show"
    assert _hits(body, "accuracy_by_type"), "no per-field accuracy to show"
    return f"{accuracy}% vs {baseline}% baseline on {evaluated} cases"


def check_help_search(body: dict) -> str:
    """The help drawer, and its tenant scoping.

    A dropped eligibility filter fails open — more articles, no error —
    so this asserts on ownership, not just that results came back.
    """
    articles = _hits(body, "articles", "results", "hits")
    assert articles, "help search returned nothing"
    leaked = [a for a in articles
              if a.get("customer_id") not in (None, "*", DEFAULT_CUSTOMER)]
    assert not leaked, \
        f"help leaked another tenant's articles: {[a.get('article_id') for a in leaked]}"
    return f"{len(articles)} articles, correctly scoped"


def check_multitenancy_landing(body: dict) -> str:
    """The landing view that makes the multi-tenant point."""
    assert body, "multitenancy landing is empty"
    return f"{len(body)} sections"


STEPS: list[Step] = [
    Step("health", "/api/health", check_health),
    Step("customers", "/api/customers", check_customers),
    Step("invoices/pending", "/api/invoices/pending", check_invoices_pending,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("formfill/templates", "/api/formfill/templates", check_formfill_templates,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("rules/candidates", "/api/rules/candidates", check_rule_candidates,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("matching/pairs", "/api/matching/pairs", check_matching_pairs,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("anomalies/scan", "/api/anomalies/scan", check_anomalies,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("quality/overview", "/api/quality/overview", check_quality_overview,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("quality/predictions", "/api/quality/predictions", check_quality_predictions,
         {"customer_id": DEFAULT_CUSTOMER}),
    Step("help/search", "/api/help/search", check_help_search,
         {"customer_id": DEFAULT_CUSTOMER, "q": "cost centre"}),
    Step("multitenancy/landing", "/api/multitenancy/landing", check_multitenancy_landing),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"server URL (default {DEFAULT_BASE})")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="per-step timeout in seconds (v2 cold views are slow)")
    args = parser.parse_args()

    try:
        httpx.get(f"{args.base}/api/health", timeout=10)
    except httpx.HTTPError:
        print(f"No server at {args.base}. Start one with: ./do dev   (or ./do dev-v2)",
              file=sys.stderr)
        return 2

    print(f"Demo path — {args.base}, {len(STEPS)} steps\n")
    failures: list[tuple[str, str]] = []
    slow: list[tuple[str, float]] = []

    with httpx.Client(base_url=args.base, timeout=args.timeout) as http:
        for step in STEPS:
            started = time.monotonic()
            try:
                response = http.get(step.path, params=step.params)
                response.raise_for_status()
                summary = step.check(response.json())
            except (httpx.HTTPError, ValueError, AssertionError, KeyError) as exc:
                elapsed = time.monotonic() - started
                failures.append((step.name, f"{type(exc).__name__}: {exc}"))
                print(f"  FAIL  {step.name} ({elapsed:.1f}s)")
                print(f"        {type(exc).__name__}: {exc}")
                continue

            elapsed = time.monotonic() - started
            if elapsed > SLOW_SECONDS:
                slow.append((step.name, elapsed))
            marker = "SLOW" if elapsed > SLOW_SECONDS else "ok  "
            print(f"  {marker}  {step.name:<26} {summary}  ({elapsed:.1f}s)")

    print()
    if slow:
        print(f"{len(slow)} step(s) over {SLOW_SECONDS:.0f}s — warm the demo before presenting "
              "(see the v2 appendix in docs/demo-script.md):")
        for name, elapsed in slow:
            print(f"  {name} — {elapsed:.1f}s")
        print()

    if failures:
        print(f"{len(failures)} of {len(STEPS)} demo steps FAILED:")
        for name, reason in failures:
            print(f"  {name}: {reason}")
        return 1

    print(f"All {len(STEPS)} demo steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
