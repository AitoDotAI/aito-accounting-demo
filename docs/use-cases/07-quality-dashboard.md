# Quality dashboard — `_evaluate` for real accuracy

![Prediction Quality](../../screenshots/08-quality-predictions.png)

*Pick a domain (Invoice / Payment / Help), a target field, the
input features. The page runs `_evaluate` with `select: [...,
"cases"]` against a held-out test sample and renders a green/red
diff table per case, with KPIs vs the always-predict-majority
baseline.*

**Companion to [aito-demo's quality monitoring](https://github.com/AitoDotAI/aito-demo/blob/main/docs/use-cases/10-quality-monitoring.md)** — same `_evaluate` operator, surfaced as a per-case table the
operator can drill.

## Overview

Most ML systems' "accuracy %" is a single aggregate number with
no way to inspect which predictions were wrong and why. Aito's
`_evaluate` returns per-case rows so the operator can see
exactly which test invoices were mispredicted.

This view is the configurator + result table for that operator.

## How it works

### The query

```python
# src/evaluation_service.py — run_evaluation()
client._request("POST", "/_evaluate", json={
    "testSource": {
        "from": "invoices",
        "where": {"customer_id": customer_id},
        "limit": limit,                           # test set size
    },
    "evaluate": {
        "from": "invoices",
        "where": {
            "customer_id": customer_id,
            **{f: {"$get": f} for f in input_fields},   # binding
        },
        "predict": predict,
    },
    "select": [
        "accuracy", "baseAccuracy", "accuracyGain",
        "meanRank", "geomMeanP",
        "testSamples", "trainSamples",
        "cases",                                  # per-test-case rows
    ],
})
```

`{$get: "fieldname"}` is Aito's binding syntax: at evaluation time
the where clause picks up each test row's field value.

### Per-case shape

Each `cases[]` entry has:

```json
{
  "testCase": { /* full test row */ },
  "accurate": true,
  "top": {"feature": "6200", "$p": 0.91},
  "correct": {"feature": "6200", "$p": 0.91}
}
```

`accurate` = true iff `top.feature == correct.feature`. The page
renders the cases table with green rows for `accurate` and red
rows otherwise, so the user can scan for systematic mispredictions.

### KPIs

- **Accuracy** — share of cases with `accurate=true`
- **Baseline accuracy** — always-predict-the-majority-value
  (`baseAccuracy`)
- **Gain** — accuracy − baseline
- **Mean rank** — average position of the correct answer in the
  prediction list (1 = always top)
- **Geom mean p** — geometric mean of predicted probability for
  the correct answer (calibration check)

## Domain catalog

The page lets the user switch between three domains, each with its
own predict targets and input fields:

```python
# src/evaluation_service.py — DOMAINS
"invoices": {
    "predict_targets": ["gl_code", "approver", "cost_centre", "category", "vat_pct", "payment_method"],
    "input_fields":    ["vendor", "amount", "category", "description", ...],
},
"matching": {
    "predict_targets": ["vendor_name", "invoice_id"],
    "input_fields":    ["description", "amount", "bank"],
},
"help": {
    "predict_targets": ["clicked", "article_id"],
    "input_fields":    ["page", "article_id", "query"],
},
```

## Performance

- `_evaluate` with 50–100 samples ≈ 5–10 s. The operator runs
  leave-one-out cross-validation per test case.
- The page caches results per (domain, predict, input_fields,
  limit) tuple; flipping back to a previous configuration is
  instant.

## Out of scope

- **Live regression alerts.** The page is point-in-time; no
  alerting on a drop. A scheduled cron + threshold would be the
  next step.
- **Per-segment accuracy.** Aggregate only; no "accuracy on
  vendors with < 10 invoices vs > 100".
