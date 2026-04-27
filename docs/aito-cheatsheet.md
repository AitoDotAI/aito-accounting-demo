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
| `_predict` | Predict a field value given known fields | Invoice Processing, Smart Form Fill, Anomaly Detection |
| `_match` | Find related records across linked tables | Payment Matching |
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

## Pattern: Payment matching with `_match`

**Query:**
```json
{
  "from": "bank_transactions",
  "where": {
    "description": "KESKO OYJ HELSINKI",
    "amount": 4220
  },
  "match": "invoice_id",
  "limit": 3
}
```

**Response shape:**
```json
{
  "offset": 0,
  "total": 230,
  "hits": [
    {
      "$p": 0.19,
      "invoice_id": "INV-2628",
      "vendor": "Kesko Oyj",
      "amount": 1599.57,
      "gl_code": "4400"
    }
  ]
}
```

**Key:** `_match` traverses the schema link from
`bank_transactions.invoice_id → invoices.invoice_id` and returns
full invoice rows ranked by association strength. Unlike `_predict`
(which guesses a single field value), `_match` finds which existing
records best relate to the given context.

**Requires:** A `link` property on the foreign key column in the
schema: `"invoice_id": {"type": "String", "link": "invoices.invoice_id"}`

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
- **No separate model file** — Aito predicts directly from indexed data.
  Indexing happens on ingest; there is no model training step, no
  pipeline, no waiting. Add a row, the next prediction reflects it.

## Pattern: Multi-tenancy

Single-table multi-tenancy: every query carries `customer_id` in
the where clause. Aito treats this as a conditional probability
filter, so two customers using the same vendor get different
predictions.

```javascript
{
  from: "invoices",
  where: { customer_id: "CUST-0000", vendor: "Telia Finland" },
  predict: "gl_code",
}
```

The `customer_id` column is indexed; `_search`/`_predict`/`_relate`
all stay flat across customer sizes (measured: ~85 ms for 20-hit
search whether the customer has 16K or 125 invoices).

## Pattern: Recommendations with `_recommend`

For ranking by historical click-through rate (help articles, product
suggestions), use `_recommend` with `goal:{clicked: true}` over an
impressions table.

```javascript
{
  from: "help_impressions",
  where: { customer_id: "CUST-0000", page: "/invoices" },
  recommend: "article_id",
  goal: { clicked: true },
  limit: 5,
}
```

For session-aware "users who read X also read Y", chain via
`prev_article_id`:

```javascript
{
  from: "help_impressions",
  where: { customer_id: "CUST-0000", prev_article_id: "ART-INVOICES-101" },
  recommend: "article_id",
  goal: { clicked: true },
  limit: 4,
}
```

`_recommend` returns top hits with `article_id` and `$p` at the top
level — no nested `feature` field like `_predict`.

## Pattern: Per-case evaluation results

`_evaluate` with `select: ["accuracy", "baseAccuracy", "geomMeanP",
"testSamples", "cases"]` returns per-test-case rows so you can build
a green/red diff table, not just an aggregate accuracy.

```javascript
{
  testSource: { from: "invoices", where: {...}, limit: 100 },
  evaluate: { from: "invoices", where: {..., vendor: {$get: "vendor"}}, predict: "gl_code" },
  select: ["accuracy", "baseAccuracy", "geomMeanP", "testSamples", "cases"],
}
```

Each `cases[]` entry has:
- `testCase` — the full row being predicted
- `accurate` — boolean (top prediction matched ground truth)
- `top: {feature, $p}` — what Aito predicted
- `correct: {feature, $p}` — what the ground truth was

NOT `case.$value` or `case.predicted` — those keys come from a
different operator's response shape.

## Gotchas

- `_predict` returns the value in `feature`, not in a key named after
  the predicted field. Always read `hit["feature"]`, not `hit["gl_code"]`.
- `_recommend` returns the predicted column directly at top level
  (e.g. `hit["article_id"]`, not `hit["feature"]`). Different from
  `_predict`.
- `_recommend` does NOT accept `select: ["$p", "feature"]` — returns
  400 "field 'feature' not found." Use the default response shape.
- `_relate` does not accept `select` — it always returns the full
  statistical breakdown (related, condition, lift, fs, ps, info, relation).
- `_relate`'s response shape: `relate` field is the *condition*,
  `to` would be invalid. Use `relate: <field>` and the condition
  comes from the `where` clause.
- Field names in queries must match the Aito schema exactly (case-sensitive).
- `_predict` with `select` only supports `$p`, `feature`, `field`, `$why`.
  Using the field name in select causes a "field not found" error.
- `_recommend` may relax the where filter and return rows outside
  the requested constraint (e.g. articles for other customers). If
  isolation matters, post-filter the result against the eligibility
  set instead of trusting the where to be hard.
- `_evaluate` is the slow operator (~8 s for 50 samples). It runs
  leave-one-out cross-validation at query time. Precompute and
  cache aggressively.
