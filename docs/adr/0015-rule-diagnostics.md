# 0015. Rule diagnostics — explain & refine a rule's exceptions

**Date:** 2026-06-24
**Status:** accepted

## Context

Rule Mining (ADR 0014) surfaces a rule, its exact support (e.g. `K.
Itäluoma AND maintenance → GL 1600`, 322/353 = 91%), and a drill-down
listing the matching invoices with exceptions flagged. But the drill-down
stops at *which* invoices disagree — it doesn't say *why*, or what to do
about it. An operator deciding whether to promote a 91% rule needs to know:
are the 31 exceptions a coherent sub-pattern (so the rule can be tightened
to ~100%), or just random noise (so 91% is the ceiling)?

## Decision

Add a **diagnostic** that, within the rule's matched population, relates
the *remaining input features* (intake inputs not already in the rule's
clauses) to the rule's output value. Each feature value's `lift` toward
the output splits cleanly:

- **lift > 1** — the feature value goes with *agreement* (the rule holds).
- **lift < 1** — the feature value goes with *disagreement* (it marks the
  exceptions).
- **lift ≈ 1** — neutral; the exceptions don't track this feature.

### Aito usage

One `_relate` over the clause-scoped population, conditioned on the output
(`$on` expresses "output **given** the rule's clauses"):

```json
{
  "from": { "from": "invoices", "where": { "customer_id": "…" } },
  "where": { "$on": [ { "gl_code": "1600" },
                      { "vendor": "K. Itäluoma Oy", "category": "maintenance" } ] },
  "relate": ["amount_band", "vendor_country"],
  "select": ["related", "lift", "fs"],
  "orderBy": "lift"
}
```

(Equivalently: pin the clauses in a nested `from`, the output in `where`.)
Each hit's `fs.fOnCondition / fs.f` gives the exact agree-count for that
feature value.

Verified live:
- `K. Itäluoma AND maintenance → 1600`: `amount_band=medium` → lift 0.02
  (0/26 agree). The exceptions are exactly the non-large invoices →
  **suggest adding `amount_band="large"`** to refine the rule to ~100%.
- `Dottoressa AND consulting → 5400`: every lift ≈ 1.00 → exceptions are
  random (the 2% GL noise), no refinement possible. Reported as such.

### Backend

- `AitoClient.relate_features(table, population_where, target, relate_fields)`
  — the thin wrapper for the diagnostic `_relate`.
- `rulemining_service.diagnose_rule(...)` — interprets the response into
  `explains_exceptions` (lift < 0.9), `explains_agreement` (lift > 1.1),
  and an optional `suggestion` (the dominant agreeing feature value to add
  as a clause). Pure-ish; the interpretation is unit-tested with canned
  `_relate` responses.
- `GET /api/rules/diagnose` returns the above for a rule.

### Frontend

- A diagnostic panel beside the drill-down's invoice list: "What explains
  the exceptions" / "What the agreements share", each a short feature list
  with lift and agree-count, plus the suggested refinement chip.
- Clicking an invoice row expands its full field detail (description,
  vendor_country, cost_centre, amount_band, …) — useful for eyeballing an
  exception the diagnostic flags.

## Acceptance criteria

- Opening a rule's drill-down shows, for a structurally-explained rule,
  the feature(s) that mark its exceptions and a concrete "add clause X"
  suggestion; for a noise rule, "exceptions appear random."
- The diagnostic relates **inputs only** (consistent with ADR 0014) — it
  never suggests conditioning on an output.
- Clicking an invoice reveals its full details.
- `diagnose_rule` is unit-tested for the structural, noise, and
  no-remaining-inputs cases.

## Out of scope

- Auto-applying a suggested refinement (one click to expand the rule) —
  the suggestion is advisory; promotion/editing stays manual.
- Diagnosing with non-input fields (amount, processor) for forensic
  interest — inputs only, since the output is a routing rule.
