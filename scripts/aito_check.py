#!/usr/bin/env python3
"""Sanity-check every Aito query pattern the demo depends on.

    ./do aito-check          # against the v1 API (production path)
    ./do aito-check --v2     # against the v2 API in env $AITO_V2_ENV

This is the check CLAUDE.md calls for: run all Aito queries against the
dataset and assert the responses are shaped the way the app assumes.
Unit tests can't do this job — they stub the client, so they pass while
the live API quietly changes what it returns.

Every assertion here exists because something actually broke:

  - `$why` factors were silently dropped when v2 changed how a
    proposition is encoded. The popup rendered a base rate and nothing
    else, with no error anywhere. (check_why_factors_parse)
  - `_recommend` silently discarded a tenant-scoping filter and returned
    another customer's private articles with a 200. (check_help_is_tenant_scoped)
  - `_evaluate`'s baseline ignored the query's `where`, inflating the
    displayed accuracy gain from +52pp to +81pp. (check_evaluate_baseline_is_scoped)
  - `$patterns` returned propositions as unparseable strings.
    (check_rule_mining_returns_structured_propositions)

So the theme is: a wrong answer that still returns 200. Each check
asserts on the *content* — a probability in range, a row count, a
present field — never merely that the call succeeded.

Adding a new Aito query pattern? Add its assertion here in the same PR.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

# Run as a script, so the project root isn't on the path yet — same
# bootstrap as data/precompute_predictions.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A customer with enough history to make predictions meaningful, and a
# vendor whose GL coding is near-deterministic in the fixtures (97.8%
# of its invoices are 4400). If the fixtures are regenerated these may
# need updating — they are asserted on, not guessed at.
CUSTOMER = "CUST-0000"
DOMINANT_VENDOR = "EEE Energy Ecology Engineering Oy"
DOMINANT_VENDOR_GL = "4400"
# A vendor/category pair whose rule has real exceptions — the case the
# `$on` diagnostic exists to explain.
RULE_VENDOR = "K. Itäluoma Oy"
RULE_CATEGORY = "maintenance"
RULE_GL = "1600"


class CheckFailed(AssertionError):
    """A query returned something the app would have mishandled."""


def require(condition: bool, message: str) -> None:
    """Assert, but with a message that names the actual value.

    Error messages here have to be diagnosable without a debugger —
    this runs in CI and in a terminal, not under a breakpoint.
    """
    if not condition:
        raise CheckFailed(message)


def require_probability(value: object, label: str) -> float:
    """A probability must be a real number in [0, 1].

    Aito returns JSON numbers, so a string here means a response-shape
    change, and a value outside [0, 1] means we are reading the wrong
    field (a raw count or a lift, both of which have appeared where a
    probability was expected).
    """
    require(isinstance(value, (int, float)), f"{label} is not a number: {value!r}")
    probability = float(value)  # type: ignore[arg-type]
    require(0.0 <= probability <= 1.0, f"{label} out of [0,1]: {probability}")
    return probability


# ── Checks ───────────────────────────────────────────────────────────
#
# Each takes the client and returns a one-line summary of what it saw.
# Raising CheckFailed fails the run; anything else propagates as an
# error, which also fails the run. Nothing is caught and ignored.


def check_schema_has_demo_tables(client) -> str:
    """Every table the demo queries exists and invoices is intact."""
    schema = client.get_schema()
    tables = schema.get("schema", schema)
    require(isinstance(tables, dict), f"schema is not a dict: {type(tables).__name__}")

    expected = {"invoices", "customers", "employees", "bank_transactions",
                "overrides", "help_articles", "help_impressions"}
    missing = expected - set(tables)
    require(not missing, f"schema is missing tables: {sorted(missing)}")

    columns = tables["invoices"].get("columns", {})
    for column in ("customer_id", "vendor", "gl_code", "approver", "description", "amount"):
        require(column in columns, f"invoices is missing column '{column}'")
    return f"{len(tables)} tables, invoices has {len(columns)} columns"


def check_search_returns_rows(client) -> str:
    """The most basic query: a tenant's invoices come back non-empty.

    `total` matters as much as `hits` — several endpoints page on it,
    and a silently-zero total renders an empty view rather than an error.
    """
    result = client.search("invoices", {"customer_id": CUSTOMER}, limit=5)
    hits = result.get("hits", [])
    total = result.get("total", 0)
    require(hits, f"no invoices for {CUSTOMER} — the demo's main view would be empty")
    require(total > len(hits), f"total ({total}) should exceed a 5-row page")
    for hit in hits:
        require(hit.get("customer_id") == CUSTOMER,
                f"search leaked another tenant's row: {hit.get('customer_id')}")
    return f"{total} invoices, page of {len(hits)} correctly scoped"


def check_predict_gl_code(client) -> str:
    """GL prediction — the demo's headline capability.

    Asserts the *answer*, not just the shape: this vendor is 97.8%
    coded to one GL, so a top-1 that isn't 4400 means inference broke.
    """
    result = client.predict(
        "invoices", {"customer_id": CUSTOMER, "vendor": DOMINANT_VENDOR}, "gl_code")
    hits = result.get("hits", [])
    require(hits, f"predict returned no candidates for '{DOMINANT_VENDOR}'")

    top = hits[0]
    value = top.get("feature", top.get("$value"))
    require(value == DOMINANT_VENDOR_GL,
            f"top GL for '{DOMINANT_VENDOR}' is {value!r}, expected {DOMINANT_VENDOR_GL!r}")
    probability = require_probability(top.get("$p"), "top prediction $p")
    require(probability > 0.5,
            f"top $p is {probability:.3f} — too flat for a 97.8%-deterministic vendor")

    previous = 1.0
    for hit in hits:
        current = require_probability(hit.get("$p"), "candidate $p")
        require(current <= previous + 1e-9, "candidates are not sorted by descending $p")
        previous = current
    return f"{DOMINANT_VENDOR_GL} @ {probability:.3f}, {len(hits)} candidates ranked"


def check_predict_approver(client) -> str:
    """Approver routing — the second predicted field."""
    result = client.predict(
        "invoices", {"customer_id": CUSTOMER, "vendor": DOMINANT_VENDOR}, "approver")
    hits = result.get("hits", [])
    require(hits, "predict returned no approver candidates")
    probability = require_probability(hits[0].get("$p"), "top approver $p")
    value = hits[0].get("feature", hits[0].get("$value"))
    require(isinstance(value, str) and value, f"approver value is empty: {value!r}")
    return f"{value} @ {probability:.3f}"


def check_why_factors_parse(client) -> str:
    """The explanation must survive parsing into per-feature factors.

    This is the regression that made the check suite worth writing.
    v2 encodes a proposition as a bare value grouped under `$group`;
    v1 wraps it in an operator and groups under `$and`. The parser knew
    only v1's encoding, so on v2 every factor was discarded and the
    popup showed a lone base rate — the demo's differentiator, silently
    empty, with a 200 and no log line.

    A base probability alone is not an explanation, so that is exactly
    what this asserts against.
    """
    from src.invoice_service import _extract_why_factors

    result = client.predict(
        "invoices", {"customer_id": CUSTOMER, "vendor": DOMINANT_VENDOR}, "gl_code")
    why = result.get("hits", [{}])[0].get("$why")
    require(why is not None, "predict returned no $why — the explanation popup would be empty")

    factors = _extract_why_factors(why)
    require(factors, "$why parsed to zero factors — the tree shape changed")
    require(len(factors) > 1,
            f"$why parsed to only {len(factors)} factor(s) — evidence factors were dropped, "
            "leaving just the base rate (this is what the v1/v2 encoding change did)")

    patterns = [f for f in factors if f.get("type") == "pattern"]
    require(patterns, "$why has a base probability but no evidence factors")
    for factor in patterns:
        require(factor.get("propositions"),
                f"pattern factor carries no propositions (this is the empty-parse "
                f"signature — the tree was walked but nothing was extracted): {factor}")
        require(isinstance(factor.get("lift"), (int, float)), f"factor has no lift: {factor}")
    return f"{len(factors)} factors, {len(patterns)} evidence pattern(s)"


def check_relate_returns_statistics(client) -> str:
    """`relate` must carry the counts the drill-downs divide by.

    `fs` went missing once on the `$on` form; every ratio downstream
    became a ZeroDivisionError guard returning 0, which reads as
    "no correlation" rather than "no data".
    """
    result = client.relate("overrides", {"customer_id": CUSTOMER}, "corrected_value")
    hits = result.get("hits", [])
    require(hits, f"relate returned nothing for {CUSTOMER}'s overrides")

    first = hits[0]
    require("related" in first, f"relate hit has no 'related': {sorted(first)}")
    counts = first.get("fs", {})
    require(counts, f"relate hit has no 'fs' counts: {sorted(first)}")
    for field in ("f", "fCondition"):
        require(field in counts, f"fs is missing '{field}': {sorted(counts)}")
        require(counts[field] >= 0, f"fs.{field} is negative: {counts[field]}")
    return f"{len(hits)} relations, fs present"


def check_rule_mining_returns_structured_propositions(client) -> str:
    """Mined patterns must be JSON, not stringified pseudo-JSON.

    v2 briefly returned `related` as a string with unquoted keys and
    non-breaking spaces. Every client needed a bespoke parser, so this
    asserts the structure `parse_conjunction` actually consumes.
    """
    from src.rulemining_service import parse_conjunction

    result = client.relate_patterns(
        "invoices", {"gl_code": RULE_GL}, ["vendor", "category"],
        where_filter={"customer_id": CUSTOMER}, k=6, limit=5)
    hits = result.get("hits", [])
    require(hits, f"no patterns mined for gl_code={RULE_GL} — rule mining would show nothing")

    first = hits[0]
    related = first.get("related")
    require(isinstance(related, dict),
            f"'related' is {type(related).__name__}, expected dict (v2 once returned a string)")
    clauses = parse_conjunction(related)
    require(clauses, f"parse_conjunction found no clauses in {related!r}")

    lift = first.get("lift")
    require(isinstance(lift, (int, float)) and lift > 0, f"lift is not a positive number: {lift!r}")
    return f"{len(hits)} patterns, top has {len(clauses)} clause(s) at lift {lift:.1f}"


def check_on_diagnostic_shows_exceptions(client) -> str:
    """The `$on` diagnostic must show values with *zero* agreement.

    A rule's exceptions are the whole point of the drill-down. When
    `$on` conditioned on the target, any value that never co-occurs
    with it had no rows and vanished — the diagnostic could not see the
    thing it exists to find.
    """
    result = client.relate_features(
        "invoices",
        {"vendor": RULE_VENDOR, "category": RULE_CATEGORY},
        {"gl_code": RULE_GL},
        ["amount_band"])
    hits = result.get("hits", [])
    require(hits, f"$on relate returned nothing for {RULE_VENDOR}/{RULE_CATEGORY}")

    for hit in hits:
        counts = hit.get("fs", {})
        require(counts, f"$on hit has no fs — exact agreement can't be computed: {sorted(hit)}")
        require("fOnCondition" in counts, f"fs is missing fOnCondition: {sorted(counts)}")

    zero_agreement = [h for h in hits if h.get("fs", {}).get("fOnCondition") == 0]
    require(zero_agreement,
            f"no zero-agreement value returned for {RULE_VENDOR}/{RULE_CATEGORY} — "
            "the exception this rule has is invisible to the diagnostic")
    return f"{len(hits)} feature values, {len(zero_agreement)} exception(s) visible"


def check_evaluate_baseline_is_scoped(client) -> str:
    """`_evaluate` metrics must respect the query's tenant scope.

    `baseAccuracy` once ignored the `where` and returned the *global*
    majority-class share (0.17) instead of the within-tenant one (0.47).
    Accuracy looked fine; the displayed *gain* was inflated from +52pp
    to +81pp — a wrong number presented confidently, which is worse
    than an error.

    The bound below is deliberately loose: it catches a baseline
    computed over the wrong population, not a small sampling
    difference.
    """
    metrics = client.evaluate({
        "testSource": {"from": "invoices", "where": {"customer_id": CUSTOMER}, "limit": 30},
        "evaluate": {
            "from": "invoices",
            "where": {"customer_id": CUSTOMER, "vendor": {"$get": "vendor"},
                      "description": {"$get": "description"}},
            "predict": "gl_code",
        },
        "select": ["accuracy", "baseAccuracy", "testSamples"],
    })
    accuracy = require_probability(metrics.get("accuracy"), "accuracy")
    baseline = require_probability(metrics.get("baseAccuracy"), "baseAccuracy")
    samples = metrics.get("testSamples")
    require(samples == 30, f"testSamples is {samples}, expected the requested 30")
    require(accuracy > baseline,
            f"accuracy {accuracy:.3f} does not beat the baseline {baseline:.3f}")
    # 0.25 is chosen to sit clearly between the two populations, not to
    # be tight: this tenant's majority GL covers ~47% of its rows, while
    # the global majority class is ~17%. v1 measures the base rate on the
    # 30-row test sample and so lands lower (~0.33) than v2, which uses
    # the training population — both pass, a global baseline does not.
    require(baseline > 0.25,
            f"baseAccuracy {baseline:.4f} looks global rather than scoped to {CUSTOMER} "
            f"(this tenant's majority GL covers ~47% of its rows; the global "
            f"majority class is ~17%)")
    return f"accuracy {accuracy:.2f} vs baseline {baseline:.2f} on {samples} rows"


def check_payment_matching_ranks(client) -> str:
    """Bank-transaction → invoice matching produces a ranked candidate.

    The demo predicts the linked `invoice_id` rather than using
    `_match`. A 128k-cardinality target makes every probability tiny,
    so this asserts ranking and range, not magnitude.
    """
    from src.matching_service import match_all

    result = match_all(client, CUSTOMER)
    pairs = result.get("pairs", [])
    require(pairs, f"matching produced no pairs for {CUSTOMER}")

    matched = [p for p in pairs if p.get("status") != "unmatched"]
    require(matched, f"all {len(pairs)} transactions came back unmatched — "
                     "the matcher ranked nothing above threshold")
    for pair in matched:
        require_probability(pair.get("confidence"), "match confidence")
        require(pair.get("bank_txn_id"), f"matched pair has no bank transaction: {pair}")
    return f"{len(matched)} matched / {len(pairs)} pairs"


def check_help_is_tenant_scoped(client) -> str:
    """Help ranking must never return another tenant's private article.

    `_recommend` once discarded the linked-field eligibility clause
    without an error, returning other customers' `internal` articles
    with a 200. A dropped filter fails *open*: more rows, no exception,
    nothing in the logs. Only a content assertion catches it, so this
    asserts on the article ids themselves.
    """
    from src.help_service import search_help

    articles = search_help(client, CUSTOMER, query="cost centre", limit=8)
    require(articles, f"help search returned nothing for {CUSTOMER}")

    leaked = [
        a for a in articles
        if a.get("customer_id") not in ("*", CUSTOMER)
    ]
    require(not leaked,
            "help returned articles belonging to another tenant: "
            f"{[a.get('article_id') for a in leaked]}")
    return f"{len(articles)} articles, all global or {CUSTOMER}'s own"


CHECKS: list[Callable[[object], str]] = [
    check_schema_has_demo_tables,
    check_search_returns_rows,
    check_predict_gl_code,
    check_predict_approver,
    check_why_factors_parse,
    check_relate_returns_statistics,
    check_rule_mining_returns_structured_propositions,
    check_on_diagnostic_shows_exceptions,
    check_evaluate_baseline_is_scoped,
    check_payment_matching_ranks,
    check_help_is_tenant_scoped,
]


def build_client(use_v2: bool):
    """The same client the app would construct for this configuration."""
    from src.config import load_config

    config = load_config()
    if not use_v2:
        from src.aito_client import AitoClient
        return AitoClient(config), "v1"

    from src.aito_v2_client import AitoV2Client

    env = os.environ.get("AITO_V2_ENV", "").strip()
    if not env:
        raise SystemExit(
            "--v2 needs AITO_V2_ENV set to the env to check (e.g. AITO_V2_ENV=v2-demo).\n"
            "Build one with: ./do v2-build")
    return AitoV2Client(config.aito_api_url, config.aito_api_key, env=env), f"v2 env '{env}'"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--v2", action="store_true",
                        help="check the v2 API in $AITO_V2_ENV instead of v1")
    parser.add_argument("--only", metavar="SUBSTRING",
                        help="run only checks whose name contains this")
    args = parser.parse_args()

    client, target = build_client(args.v2)
    checks = [c for c in CHECKS if not args.only or args.only in c.__name__]
    if not checks:
        raise SystemExit(f"no check matches --only {args.only!r}")

    print(f"Aito query sanity — {target}, {len(checks)} checks\n")
    failures: list[tuple[str, BaseException]] = []

    for check in checks:
        name = check.__name__.removeprefix("check_")
        started = time.monotonic()
        try:
            summary = check(client)
        except BaseException as exc:  # noqa: BLE001 — reported, then re-raised as a failure
            failures.append((name, exc))
            print(f"  FAIL  {name} ({time.monotonic() - started:.1f}s)")
            print(f"        {type(exc).__name__}: {exc}")
        else:
            print(f"  ok    {name:<48} {summary}  ({time.monotonic() - started:.1f}s)")

    print()
    if failures:
        print(f"{len(failures)} of {len(checks)} checks FAILED on {target}:\n")
        for name, exc in failures:
            if not isinstance(exc, CheckFailed):
                print(f"--- {name} raised unexpectedly ---")
                traceback.print_exception(type(exc), exc, exc.__traceback__)
        print("  " + "\n  ".join(name for name, _ in failures))
        return 1

    print(f"All {len(checks)} checks passed on {target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
