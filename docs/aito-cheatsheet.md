# Aito query cheatsheet

> Quick reference for Aito query patterns used in this project.
> Official docs: https://aito.ai/docs
>
> **Important:** All query shapes and response structures in this file
> have been verified against the live demo Aito instance. Do not invent
> new patterns without testing them first.

## Operators used

| Operator | Purpose | Used in |
|----------|---------|---------|
| `_predict` | Predict a field value given known fields | Invoice Processing, Payment Matching, Smart Form Fill, Anomaly Detection |
| `_relate` | Find statistical relationships between features | Rule Mining, Human Overrides |
| `_search` | Retrieve matching records | Data lookups |

## Pattern: GL code prediction

**Query:**
```json
{
  "from": "invoices",
  "where": {
    "vendor": "Kesko Oyj",
    "amount": 4220
  },
  "predict": "gl_code",
  "select": ["$p", "feature", "$why"]
}
```

**Response shape:**
```json
{
  "offset": 0,
  "total": 7,
  "hits": [
    {
      "$p": 0.91,
      "field": "gl_code",
      "feature": "4400",
      "$why": { "type": "product", "factors": [...] }
    }
  ]
}
```

**Key:** The predicted value is in `feature`, not in a key named after
the field. The `field` key tells you which column was predicted.

## Pattern: Approver prediction

Same shape as GL code, just different predict target:

```json
{
  "from": "invoices",
  "where": { "vendor": "Kesko Oyj" },
  "predict": "approver",
  "select": ["$p", "feature", "$why"]
}
```

## Pattern: Rule mining with `_relate`

**Query:**
```json
{
  "from": "invoices",
  "where": { "vendor": "Kesko Oyj" },
  "relate": "gl_code"
}
```

**Response shape:**
```json
{
  "offset": 0,
  "total": 7,
  "hits": [
    {
      "related": { "gl_code": { "$has": "4400" } },
      "condition": { "vendor": { "$has": "Kesko Oyj" } },
      "lift": 6.49,
      "fs": {
        "f": 33,
        "fOnCondition": 18,
        "fOnNotCondition": 15,
        "fCondition": 18,
        "n": 230
      },
      "ps": {
        "p": 0.14,
        "pOnCondition": 0.95,
        "pOnNotCondition": 0.07,
        "pCondition": 0.08
      }
    }
  ]
}
```

**Key fields:**
- `related` — the field value this row describes
- `lift` — how much more likely the value is given the condition
  (lift > 1 = positive correlation)
- `fs.fOnCondition` — count matching both condition and related value
  (the numerator in "18/18" support ratios)
- `fs.f` — total count of this related value (the denominator context)
- `ps.pOnCondition` — probability of related value given the condition

**Note:** `_relate` does not accept a `select` parameter. The full
statistical breakdown is always returned.

## Pattern: Anomaly detection (inverse prediction)

```json
{
  "from": "invoices",
  "where": {
    "vendor": "Fazer Bakeries",
    "amount": 22400
  },
  "predict": "gl_code",
  "select": ["$p", "feature", "$why"]
}
```

Low `$p` on the top prediction signals an anomaly — the data doesn't
match known patterns.

## Key concepts

- **$p** — probability score in [0, 1]. Higher = more confident.
- **$why** — feature-level explanation of what drove the prediction.
  Nested structure with factors and lifts.
- **feature** — the predicted value in `_predict` responses.
- **lift** — in `_relate`, how much more likely a value is given the
  condition vs the base rate. lift=6.5 means 6.5x more likely.
- **fs (frequency statistics)** — raw counts in `_relate` responses.
  `fOnCondition/f` gives exact support ratios.
- **Zero training** — Aito queries run immediately on ingested data.
  No model training step, no pipeline, no waiting.

## Gotchas

- `_predict` returns the value in `feature`, not in a key named after
  the predicted field. Always read `hit["feature"]`, not `hit["gl_code"]`.
- `_relate` does not accept `select` — it always returns the full
  statistical breakdown (related, condition, lift, fs, ps, info, relation).
- Field names in queries must match the Aito schema exactly (case-sensitive).
- `_predict` with `select` only supports `$p`, `feature`, `field`, `$why`.
  Using the field name in select causes a "field not found" error.
