# Rule mining — discover patterns + chain into compounds

![Rule Mining](../../screenshots/04-rulemining.png)

*Run `_relate` over each customer's invoice history to find
deterministic patterns. Each candidate row expands into a chained
`_relate` for compound sub-patterns under that conjunction.*

**Companion to [aito-demo's `_relate` use case](https://github.com/AitoDotAI/aito-demo/blob/main/docs/use-cases/07-data-analytics.md)** —
same operator, applied to per-tenant rule discovery.

## Overview

Mined rules capture the high-precision routing patterns ("vendor
X always books to GL Y") so the production system can short-circuit
the live `_predict` call. Aito's `_relate` returns the support
ratio (4123 / 4156) and lift (38×) for each candidate, ready to
inspect and promote.

## How it works

### Top-level patterns

```python
# src/rulemining_service.py — mine_rules()
for field in ["category", "vendor_country", "vendor"]:
    for value in distinct_values(field, customer_id):
        result = client.relate(
            "invoices",
            {"customer_id": customer_id, field: value},
            "gl_code",
        )
        # Each hit: {related: {gl_code: {$has: "..."}}, lift, fs:
        # {fOnCondition, fCondition, ...}, ps: {p, pOnCondition, ...}}
```

The page shows the top hit per (field, value) tuple. Support ratio
≥ 0.95 with at least 5 cases promotes a candidate to "strong".

### Compound sub-patterns (chained `_relate`)

Click a candidate row → the page fires `/api/rules/sub_patterns`,
which runs additional `_relate` calls with the discovered
conjunction baked into the where clause:

```python
# src/app.py — rules_sub_patterns()
for field in ["category", "cost_centre", "approver", "payment_method", "due_days"]:
    if field == condition_field or field == target_field:
        continue
    sub = aito.relate(
        "invoices",
        {
            "customer_id": customer_id,
            condition_field: condition_value,
            target_field: target_value,
        },
        field,
    )
```

Output: `vendor=Telia & gl_code=6200 → approver=Mikael H.
(701/8000, 15.8× lift)` — the second-order pattern that wasn't
visible at the headline level.

### Why this is "poor man's pattern proposition"

Aito's `_relate` takes a single conjunction in the LHS (the where
clause). To discover rules whose LHS is a conjunction of *multiple*
discovered facts, we chain calls — fix the conjunction in `where`
and ask `_relate` against each remaining input field. That's the
workaround until Aito grows a first-class pattern proposition.

## Demo flow

1. Page loads with ~15 candidate rules ranked by support × coverage.
2. Click the chevron on a row → inline panel shows the chained
   sub-patterns. Each takes ~80 ms (`_relate` baseline) so the full
   panel fires in ~400 ms.
3. Click "view invoices →" on the right → modal opens with the
   actual matching invoices, marked green/red by whether the rule
   would fire correctly.
4. Click "promote" (production) → rule lands in the rules table
   for the live prediction path to short-circuit.

## Aito features used

- **`_relate`** — the rule-discovery operator.
- **Schema links** — the chained drill walks `invoice_id.vendor` to
  link override-table queries back to invoice fields.
- **Support / lift / counts** — exact, computed at index time, not
  ML estimates.

## Performance

- One `_relate` call ≈ 80–200 ms (depends on cardinality).
- Chained drill: 5 calls per row, fired lazily on expand, cached
  per-rule client-side.

## Out of scope

- **Auto-promote.** A real product would promote candidates with
  precision ≥ 0.99 over a stable window. The demo shows the
  candidates list but leaves promotion manual.
- **Rule decay.** No drift detection — `quality/rules/drift` shows
  weekly precision but the candidate list itself is point-in-time.
