#!/usr/bin/env python3
"""Audit every view for results that are WRONG but still return 200.

    ./do audit                       # against v1 (production path)
    ./do audit --v2 --env v2-demo    # against a v2 environment
    ./do audit --customer CUST-0007

`aito-check` asks whether Aito answered. `verify-demo` asks whether the
endpoint returned content. Neither asks whether the content is
*coherent* — and that is the gap a live demo fell into: Payment
Matching showed an explanation belonging to a different invoice, under
an equation reading `0% x 0.7 = 58%`. Every call was a 200. Every test
passed.

So this checks the things a response can contradict about itself:

  - an explanation must describe the value it is shown under
  - parts must sum to their stated total
  - a ratio must equal its own numerator over its own denominator
  - probabilities must be in [0, 1] and sorted where claimed sorted
  - a flag must carry the text the card renders
  - a tenant's results must contain only that tenant's rows

Each finding names the view, what disagreed, and the two values, so it
can be triaged without rerunning anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aito_client import AitoClient  # noqa: E402
from src.config import load_config  # noqa: E402

FINDINGS: list[tuple[str, str]] = []
CHECKED = 0


def bad(view: str, message: str) -> None:
    FINDINGS.append((view, message))


def ok(_view: str) -> None:
    global CHECKED
    CHECKED += 1


def check(view: str, condition: bool, message: str) -> bool:
    """Record a coherence check. Returns the condition, so callers can skip
    dependent checks once one has already failed."""
    global CHECKED
    CHECKED += 1
    if not condition:
        bad(view, message)
    return condition


def probability(view: str, value, label: str) -> None:
    check(view, isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0,
          f"{label} is not a probability in [0,1]: {value!r}")


def why_describes(view: str, factors: list[dict], expected_value: str, context: str) -> None:
    """The defect that reached a demo: an explanation for a different value."""
    base = [f for f in (factors or []) if f.get("type") == "base"]
    for b in base:
        target = b.get("target_value")
        check(view, target in (None, expected_value),
              f"{context}: explanation describes {target!r} but is shown under "
              f"{expected_value!r}")
        p = b.get("base_p")
        if p is not None:
            check(view, isinstance(p, (int, float)) and 0.0 <= p <= 1.0,
                  f"{context}: base_p not in [0,1]: {p!r}")
    for f in (factors or []):
        if f.get("type") == "pattern":
            lift = f.get("lift")
            check(view, isinstance(lift, (int, float)) and lift > 0,
                  f"{context}: pattern lift is not a positive number: {lift!r}")
            check(view, bool(f.get("propositions") or f.get("highlights")),
                  f"{context}: pattern card has nothing to render")


# ── Views ────────────────────────────────────────────────────────────


def audit_invoice_processing(client, customer: str) -> str:
    from src.invoice_service import predict_batch

    rows = client.search("invoices", {"customer_id": customer, "routed": False},
                         limit=12).get("hits", [])
    if not rows:
        rows = client.search("invoices", {"customer_id": customer}, limit=12).get("hits", [])
    check("invoices", bool(rows), "no invoices to predict")
    preds = predict_batch(client, rows[:8])
    check("invoices", bool(preds), "predict_batch returned nothing")

    for p in preds:
        d = p.to_dict() if hasattr(p, "to_dict") else p
        iid = d.get("invoice_id")
        probability("invoices", d.get("gl_confidence"), f"{iid} gl_confidence")
        probability("invoices", d.get("approver_confidence"), f"{iid} approver_confidence")
        check("invoices", d.get("source") in ("rule", "aito", "review"),
              f"{iid}: unknown source {d.get('source')!r}")

        for field, alts in (("gl_code", d.get("gl_alternatives") or []),
                            ("approver", d.get("approver_alternatives") or [])):
            values = [a.get("value") for a in alts]
            check("invoices", len(values) == len(set(values)),
                  f"{iid}: duplicate {field} alternatives {values}")
            confs = [a.get("confidence", 0) for a in alts]
            check("invoices", confs == sorted(confs, reverse=True),
                  f"{iid}: {field} alternatives not sorted by confidence: {confs}")
            # The top alternative should be the value actually shown.
            # Compare against `display`, not `value`: the approver field
            # carries a rendered label ("AP / Sanna Lehtinen") while the
            # alternative keeps the raw name alongside the same label.
            if alts and d.get(field) is not None:
                shown = d.get(field)
                top = alts[0]
                check("invoices", shown in (top.get("value"), top.get("display")),
                      f"{iid}: shows {field}={shown!r} but the top "
                      f"alternative is {top.get('value')!r} / {top.get('display')!r}")
            for a in alts:
                why_describes("invoices", a.get("why") or [], a.get("value"),
                              f"{iid} {field} alt {a.get('value')!r}")
    return f"{len(preds)} invoices predicted"


def audit_rule_mining(client, customer: str) -> str:
    from src.rulemining_service import mine_rules

    result = mine_rules(client, customer_id=customer)
    cands = result.get("candidates") or result.get("rules") or []
    check("rules", bool(cands), "rule mining produced no candidates")

    for c in cands:
        name = c.get("rule_name") or c.get("display") or "?"
        match_n, total_n = c.get("support_match"), c.get("support_total")
        if not check("rules", isinstance(match_n, int) and isinstance(total_n, int),
                     f"{name}: support counts are not integers "
                     f"({match_n!r}/{total_n!r})"):
            continue
        check("rules", total_n > 0, f"{name}: support_total is {total_n}")
        check("rules", match_n <= total_n,
              f"{name}: support_match {match_n} exceeds support_total {total_n}")
        ratio = c.get("support_ratio")
        if ratio is not None and total_n:
            expected = match_n / total_n
            check("rules", abs(float(ratio) - expected) < 0.02,
                  f"{name}: support_ratio {ratio} disagrees with "
                  f"{match_n}/{total_n} = {expected:.3f}")
        strength = c.get("strength")
        if strength == "strong" and ratio is not None:
            check("rules", float(ratio) >= 0.5,
                  f"{name}: labelled 'strong' at support_ratio {ratio}")
    return f"{len(cands)} rule candidates"


def audit_matching(client, customer: str) -> str:
    from src.matching_service import match_all

    result = match_all(client, customer)
    pairs, metrics = result.get("pairs", []), result.get("metrics", {})
    check("matching", bool(pairs), "matching produced no pairs")

    counted = {"matched": 0, "suggested": 0, "unmatched": 0}
    for p in pairs:
        status = p.get("status")
        if status in counted:
            counted[status] += 1
        probability("matching", p.get("confidence"), f"{p.get('bank_txn_id')} confidence")
        if status == "unmatched":
            check("matching", not p.get("invoice_id"),
                  f"{p.get('bank_txn_id')}: unmatched but carries invoice "
                  f"{p.get('invoice_id')!r}")
        else:
            check("matching", bool(p.get("invoice_id")),
                  f"{p.get('bank_txn_id')}: status {status} with no invoice")
            why_describes("matching", p.get("explanation") or [], p.get("invoice_id"),
                          f"pair {p.get('bank_txn_id')}")
    for key, n in counted.items():
        check("matching", metrics.get(key) == n,
              f"metrics.{key}={metrics.get(key)} but {n} pairs have that status")
    check("matching", metrics.get("total") == len(pairs),
          f"metrics.total={metrics.get('total')} but {len(pairs)} pairs returned")
    return f"{len(pairs)} pairs, {counted['matched']} matched"


def audit_anomalies(client, customer: str) -> str:
    from src.anomaly_service import scan_all

    result = scan_all(client, customer)
    flags = result.get("flags", [])
    metrics = result.get("metrics", {})
    scanned = metrics.get("scanned")
    check("anomalies", bool(scanned), f"scan reports nothing scanned: {scanned!r}")
    check("anomalies", len(flags) <= (scanned or 0),
          f"{len(flags)} flags from only {scanned} scanned invoices")
    check("anomalies", metrics.get("total") == len(flags),
          f"metrics.total={metrics.get('total')} but {len(flags)} flags returned")

    severities = {"high": 0, "medium": 0, "low": 0}
    for f in flags:
        iid = f.get("invoice_id")
        probability("anomalies", f.get("anomaly_score"), f"{iid} anomaly_score")
        check("anomalies", bool(f.get("description")), f"{iid}: flag has no description")
        check("anomalies", bool(f.get("recommendation")), f"{iid}: flag has no recommendation")
        sev = f.get("severity")
        if sev in severities:
            severities[sev] += 1
    for sev, n in severities.items():
        if sev in metrics:
            check("anomalies", metrics[sev] == n,
                  f"metrics.{sev}={metrics[sev]} but {n} flags have that severity")
    return f"{scanned} scanned, {len(flags)} flagged"


def audit_quality(client, customer: str) -> str:
    from src.quality_service import get_quality_overview

    o = get_quality_overview(client, customer)
    a = o.get("automation", {})
    total = a.get("total")
    check("quality", bool(total), f"automation covers no invoices: {total!r}")
    parts = {k: a.get(k) for k in ("rule", "aito", "human", "none")}
    if all(isinstance(v, int) for v in parts.values()) and total:
        check("quality", sum(parts.values()) == total,
              f"automation parts {parts} sum to {sum(parts.values())}, not {total}")
        for key, part in (("rule_pct", "rule"), ("aito_pct", "aito"), ("human_pct", "human")):
            pct = a.get(key)
            if pct is not None:
                expected = round(100 * parts[part] / total)
                check("quality", abs(pct - expected) <= 1,
                      f"{key}={pct} but {parts[part]}/{total} is {expected}%")
        rate = a.get("automation_rate")
        if rate is not None:
            expected = round(100 * (parts["rule"] + parts["aito"]) / total)
            check("quality", abs(rate - expected) <= 1,
                  f"automation_rate={rate} but (rule+aito)/total is {expected}%")
    return f"{total} invoices, {a.get('automation_rate')}% automated"


def audit_tenant_isolation(client, customer: str) -> str:
    """Every view is scoped by customer_id; prove no row escapes it."""
    for table in ("invoices", "bank_transactions", "overrides"):
        rows = client.search(table, {"customer_id": customer}, limit=25).get("hits", [])
        foreign = {r.get("customer_id") for r in rows} - {customer}
        check("tenancy", not foreign,
              f"{table}: returned rows for {sorted(foreign)} under a {customer} filter")
    return "invoices / bank_transactions / overrides correctly scoped"


def audit_accuracy(client, customer: str) -> str:
    """Every predictable field, scored against its own baseline.

    Coherence is not quality: a view can be perfectly self-consistent and
    still show a model that has learned nothing. A field whose accuracy
    equals its base rate is a field where the demo is claiming credit for
    guessing the majority class, and a visitor who opens it in the
    Quality matrix sees exactly that.
    """
    from src.evaluation_service import run_evaluation

    fields = ["gl_code", "approver", "cost_centre", "category", "vat_pct", "payment_method"]
    flat = []
    for field in fields:
        result = run_evaluation(client, customer, "invoices", field,
                                ["vendor", "amount", "category"], limit=40)
        if "error" in result:
            bad("accuracy", f"{field}: evaluation failed — {result['error'][:80]}")
            continue
        k = result["kpis"]
        accuracy = k["accuracy_pct"]
        baseline = k["base_accuracy_pct"]
        check("accuracy", accuracy >= baseline - 1,
              f"{field}: accuracy {accuracy}% is BELOW its base rate {baseline}%")
        if accuracy - baseline < 1.0:
            flat.append(f"{field} ({accuracy}% vs {baseline}% base)")
    if flat:
        bad("accuracy",
            "no better than guessing the majority class: " + "; ".join(flat) +
            " — offered as predict targets in the Quality matrix, so a visitor "
            "who opens one sees a model that has learned nothing")
    return f"{len(fields)} fields scored, {len(flat)} with no gain"


AUDITS = [
    ("invoice processing", audit_invoice_processing),
    ("rule mining", audit_rule_mining),
    ("payment matching", audit_matching),
    ("anomaly detection", audit_anomalies),
    ("quality dashboard", audit_quality),
    ("tenant isolation", audit_tenant_isolation),
]

# Slow (one _evaluate per field), so opt-in.
SLOW_AUDITS = [("field accuracy", audit_accuracy)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--customer", default="CUST-0000")
    parser.add_argument("--v2", action="store_true")
    parser.add_argument("--env", default="v2-demo")
    parser.add_argument("--only", help="run only audits whose name contains this")
    parser.add_argument("--accuracy", action="store_true",
                        help="also score every predictable field against its baseline "
                             "(slow: one _evaluate per field)")
    args = parser.parse_args()

    config = load_config()
    if args.v2:
        from src.aito_v2_client import AitoV2Client
        client = AitoV2Client(config.aito_api_url, config.aito_api_key, env=args.env)
        target = f"v2 env '{args.env}'"
    else:
        client = AitoClient(config)
        target = "v1"

    print(f"Portfolio coherence audit — {target}, customer {args.customer}\n")
    for name, fn in AUDITS + (SLOW_AUDITS if args.accuracy else []):
        if args.only and args.only not in name:
            continue
        before = len(FINDINGS)
        try:
            summary = fn(client, args.customer)
        except Exception as exc:  # noqa: BLE001 — a crash IS a finding
            bad(name, f"raised {type(exc).__name__}: {exc}")
            print(f"  ERROR  {name:22} {type(exc).__name__}: {exc}")
            continue
        new = len(FINDINGS) - before
        mark = "ok    " if new == 0 else f"{new} ISSUE"
        print(f"  {mark} {name:22} {summary}")

    print(f"\n{CHECKED} coherence checks run.")
    if not FINDINGS:
        print("No incoherence found.")
        return 0
    print(f"\n{len(FINDINGS)} finding(s):\n")
    for view, message in FINDINGS:
        print(f"  [{view}] {message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
