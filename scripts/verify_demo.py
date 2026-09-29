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
LIVE_BASE = "https://accounting.aito.ai"
# The customer the live demo is given on (the ModernPath brief, 30.9: "CUST-0001,
# not 0000, which has nothing to review"). Its views are precomputed.
DEFAULT_CUSTOMER = "CUST-0001"

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
    # The route writes to Aito on a cache miss (cache.set -> cache_entries).
    # --live skips it: the live smoke must never write to the demo database.
    writes_on_miss: bool = False


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

    # The demo's two beats on this view: a confident prediction with a why card
    # a person can check, and a row where Aito hesitates ("so it goes to you").
    by_aito = [i for i in invoices if i.get("source") == "aito"]
    assert by_aito, "no Aito-predicted rows, only rules: nothing to show a why card on"
    hesitant = [i for i in by_aito if float(i.get("confidence") or 1) < LOW_CONFIDENCE]
    assert hesitant, (f"no Aito row below {LOW_CONFIDENCE:.0%} confidence: the "
                      "'here it hesitates' beat has no row to point at")
    explained = [i for i in by_aito if _visible_why_cards(i)]
    assert explained, "no Aito row has a why card that survives the presentation filter"
    return (f"{len(invoices)} pending, {len(by_aito)} by Aito, {len(hesitant)} hesitant, "
            f"{len(explained)} with a visible why card")


# Below this an Aito row renders amber or red (frontend/lib/api.ts confClass).
LOW_CONFIDENCE = 0.80
# The why-card rules of frontend/lib/why-display.ts + WhyCards.tsx: a pattern
# earns a card if its lift is material and it mentions no category, raw amount
# or bare number. Mirrored here so the smoke fails when every card would fold.
_MATERIAL = 1.15
_HIDDEN_FIELDS = {"category", "amount"}


def _visible_why_cards(invoice: dict) -> list:
    import re
    alternatives = invoice.get("gl_alternatives") or [{}]
    patterns = [f for f in (alternatives[0].get("why") or []) if f.get("type") == "pattern"]

    def shown(factor: dict) -> bool:
        lift = factor.get("lift", 1.0)
        if not (lift >= _MATERIAL or lift <= 1 / _MATERIAL):
            return False
        return not any(p.get("field", "").replace("invoice_id.", "") in _HIDDEN_FIELDS
                       or re.fullmatch(r"[\d\s.,:/-]+", str(p.get("value", "")))
                       for p in factor.get("propositions", []))
    return [f for f in patterns if shown(f)]


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
    # A payload without `matched_by` predates ADR 0026: the precompute
    # has not been rebuilt, and the page would lead with lookups again.
    by_aito = [p for p in pairs if p.get("matched_by") == "aito"]
    assert len(by_aito) >= 6, (
        f"only {len(by_aito)} of {len(pairs)} payments matched by Aito — "
        "stale precompute? run ./do precompute-v2")
    return f"{len(by_aito)} by Aito, {len(matched) - len(by_aito)} by reference / {len(pairs)}"


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
    """The landing view that makes the multi-tenant point: "same vendor, four
    clients, four GL accounts". At least one card has to say exactly that; on
    29.9 the FIRST card showed four clients but only three distinct accounts."""
    assert body, "multitenancy landing is empty"
    vendors = _hits(body, "vendors")
    assert vendors, "the landing has no shared vendors"
    four_by_four = [v for v in vendors
                    if len(v.get("tenants", [])) >= 4
                    and len({t.get("gl_code") for t in v["tenants"]}) >= 4]
    assert four_by_four, "no vendor card shows four clients with four different GL accounts"
    first = vendors[0]
    note = ("" if first in four_by_four
            else f"; the first card ({first.get('vendor')}) does not: present {four_by_four[0]['vendor']}")
    return f"{len(vendors)} vendors, {len(four_by_four)} with 4 clients / 4 GLs{note}"


def check_cache_warm(body: dict) -> str:
    """The demo customer's views are precomputed: a cold view is a 30 s+ spinner
    in front of an audience, and on the live site a cold read also writes the cache."""
    cold = [k for k, v in body.items() if k.endswith("_warm") and v is not True]
    assert not cold, f"cold for {body.get('customer_id')}: {', '.join(cold)}"
    return "every view precomputed"


def steps(customer: str) -> list[Step]:
    """The demo path, in demo order, for one customer."""
    c = {"customer_id": customer}
    return [
        Step("health", "/api/health", check_health, writes_on_miss=True),
        Step("cache/status", "/api/cache/status", check_cache_warm, c),
        Step("customers", "/api/customers", check_customers),
        Step("multitenancy/landing", "/api/multitenancy/landing", check_multitenancy_landing),
        Step("invoices/pending", "/api/invoices/pending", check_invoices_pending,
             {**c, "per_page": 50}),
        Step("formfill/templates", "/api/formfill/templates", check_formfill_templates, c,
             writes_on_miss=True),
        Step("rules/candidates", "/api/rules/candidates", check_rule_candidates, c),
        Step("matching/pairs", "/api/matching/pairs", check_matching_pairs, c),
        Step("anomalies/scan", "/api/anomalies/scan", check_anomalies, c),
        Step("quality/overview", "/api/quality/overview", check_quality_overview, c),
        Step("quality/predictions", "/api/quality/predictions", check_quality_predictions, c),
        Step("help/search", "/api/help/search", check_help_search,
             {**c, "q": "cost centre"}, writes_on_miss=True),
    ]


def main() -> int:
    global DEFAULT_CUSTOMER   # the checks read it (customers, help ownership)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default=None, help=f"server URL (default {DEFAULT_BASE}, or {LIVE_BASE} with --live)")
    parser.add_argument("--live", action="store_true",
                        help=f"smoke the deployed demo ({LIVE_BASE}) read-only: skip every step that "
                             "writes to Aito on a cache miss")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER,
                        help=f"the demo customer (default {DEFAULT_CUSTOMER})")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="per-step timeout in seconds (v2 cold views are slow)")
    args = parser.parse_args()
    DEFAULT_CUSTOMER = args.customer
    args.base = args.base or (LIVE_BASE if args.live else DEFAULT_BASE)
    plan = steps(args.customer)
    skipped = [s for s in plan if args.live and s.writes_on_miss]
    plan = [s for s in plan if s not in skipped]

    try:
        # /health, not /api/health: the latter writes a cache row every minute
        httpx.get(f"{args.base}/health", timeout=30)
    except httpx.HTTPError:
        print(f"No server at {args.base}. Start one with: ./do dev   (or ./do dev-v2)",
              file=sys.stderr)
        return 2

    print(f"Demo path — {args.base}, customer {args.customer}, {len(plan)} steps"
          + (f" (read-only: skipped {', '.join(s.name for s in skipped)})" if skipped else "") + "\n")
    failures: list[tuple[str, str]] = []
    slow: list[tuple[str, float]] = []

    with httpx.Client(base_url=args.base, timeout=args.timeout) as http:
        for step in plan:
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
        print(f"{len(failures)} of {len(plan)} demo steps FAILED:")
        for name, reason in failures:
            print(f"  {name}: {reason}")
        return 1

    print(f"All {len(plan)} demo steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
