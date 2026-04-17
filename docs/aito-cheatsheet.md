# Aito query cheatsheet

> Quick reference for Aito query patterns used in this project.
> Official docs: https://aito.ai/docs

## Operators used

| Operator | Purpose | Used in |
|----------|---------|---------|
| `_predict` | Predict a field value given known fields | Invoice Processing, Payment Matching, Smart Form Fill, Anomaly Detection |
| `_relate` | Find statistical relationships between features | Rule Mining, Human Overrides |
| `_statistics` | Aggregate counts and distributions | Rule Mining, Quality views |

## Pattern: GL code prediction

```json
{
  "from": "invoices",
  "where": {
    "vendor": "Kesko Oyj",
    "amount": 4220
  },
  "predict": "GLCode",
  "select": ["$p", "GLCode", "$why"]
}
```

Response includes `$p` (probability), predicted value, and `$why`
(feature-level explanation).

## Pattern: Rule mining from unrouted invoices

```json
{
  "from": "invoices",
  "where": {
    "routed": false
  },
  "relate": "GLCode",
  "select": ["feature", "$p", "lift"]
}
```

Returns feature combinations that predict GLCode, with support counts.

## Pattern: Anomaly detection (inverse prediction)

```json
{
  "from": "invoices",
  "where": {
    "vendor": "Fazer Bakeries",
    "amount": 22400
  },
  "predict": "amount_range",
  "select": ["$p", "$why"]
}
```

Low `$p` on normally predictable fields signals an anomaly.

## Key concepts

- **$p** — probability score in [0, 1]. Higher = more confident.
- **$why** — feature-level explanation of what drove the prediction.
- **Support ratio** (e.g. 47/47) — exact historical count, not an ML
  estimate. Comes from `_relate` / `_statistics`.
- **Zero training** — Aito queries run immediately on ingested data.
  No model training step, no pipeline, no waiting.

## Gotchas

- Query shapes in this cheatsheet are verified against the demo dataset.
  Do not invent new query shapes without testing against live data first.
- `_relate` returns features sorted by lift, not by support count.
  Filter for minimum support when surfacing rule candidates.
