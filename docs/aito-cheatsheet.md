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
| `_relate` + `$patterns` | Mine AND-conjunction rules (`A & B → X`) server-side | Pattern Rule Discovery |
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

**Note:** `_relate` accepts an optional `select` to trim the returned
fields (e.g. `["related", "lift", "condition"]`); omit it to get the
full statistical breakdown. *(Verified live 2026-06-23 — an earlier
version of this note claimed `select` was unsupported; it is.)*

## Pattern: Conjunction rule discovery with `$patterns`

Mine multi-field AND-rules (`A & B → X`) server-side in a single
`_relate`. The `where` pins the prediction target X; `$patterns`
discovers the left-hand-side conjunctions. Wrap the candidate fields in
`$related` to narrow them to the top-`k` most related to X *before*
mining — this is the cost/latency knob (smaller `k` = faster, narrower
search). `to` repeats the target.

**Candidate fields must be *inputs*, not outputs.** Only put fields
known at the time the rule will be *applied* into `relate`. Mining
`gl_code` with `approver` as a candidate finds `approver=X → gl_code=Y`,
but the approver isn't known when an invoice arrives — it's assigned by
the same workflow. That's leakage; the rule can't fire. Restrict
candidates to intake inputs (vendor, category, amount_band), and mine
each *output* (gl_code, approver, …) as a **separate target** from those
same inputs. `$patterns` only mines categorical-ish fields — a numeric
`amount` is ignored, so derive a categorical `amount_band` for
amount-conditional rules (capitalization, approval thresholds).

**Query:**
```json
{
  "from": "invoices",
  "where": { "gl_code": "1600" },
  "relate": {
    "$patterns": {
      "$related": {
        "relate": ["vendor", "category", "vendor_country", "amount_band"],
        "k": 8,
        "to": { "gl_code": "1600" }
      }
    }
  },
  "select": ["related", "condition", "lift", "fs", "ps"],
  "orderBy": "lift",
  "limit": 8
}
```

**Response hit** — `related` is a copy-pasteable `$and` proposition:
```json
{
  "related": { "$and": [
    { "vendor":   { "$has": "Oy Retail Clinic Ab" } },
    { "approver": { "$has": "Matti Heikkinen" } }
  ] },
  "condition": { "gl_code": { "$has": "6200" } },
  "lift": 13.7,
  "fs": { "f": 1006, "fOnCondition": 992, "fCondition": 9130, "n": 128000 }
}
```

**`fs` is a smoothed ESTIMATE — don't display it as exact support.**
`$patterns`' `fs` comes from the re-expression learner, not a row count:
you'll see *fractional* values (`f: 836.36`) and rules rounded to
deterministic (`fOnCondition == f` → "100%") when the data actually has
exceptions. If you print that as "836 of 836" next to an exact-`_search`
drill-down, the two disagree (the drill-down surfaces a row at a
different GL). Use `$patterns` to **discover** the conjunctions, then
compute exact support with `_search` `limit:0` counts:
- **precision** = `count(clauses & GL) / count(clauses)`
- **coverage**  = `count(clauses & GL) / count(GL)`
- **lift**      = `precision / (count(GL) / count(scope))`

all scoped to the same tenant. (Live: `fs` estimated 836/836 = 100%;
exact `_search` gave 815/831 = 98.1%, the 16 exceptions visible in
drill-down.) The `lift` in the response is a fine *discovery* signal
(positive vs. anti-correlated); recompute it exactly for display.

**Multi-tenancy — scope with a nested `from`, NOT the `where`:**
Adding a filter like `customer_id` to the `where` *breaks* `$patterns`.
The mining then treats the filter as (part of) the condition — a linked
`customer_id` expands and dominates — and the support counts come back
computed over the **global** table, not the tenant. Filter the row
population with a nested `from` instead, leaving `where` as the pure
target:
```json
{
  "from": { "from": "invoices", "where": { "customer_id": "CUST-0000" } },
  "where": { "gl_code": "6200" },
  "relate": { "$patterns": { "$related": {
    "relate": ["vendor", "category", "approver"], "k": 8,
    "to": { "gl_code": "6200" }
  } } }
}
```
With this, `condition` is reliably `{gl_code: …}` and `fs.n` equals the
tenant's row count. *(Verified live 2026-06-23 — the `where`-filter form
returned `n=128000` global vs. `n=16000` for the tenant.)*

For a **plain `_relate`** (not `$patterns`) that scopes to a
sub-population *and* conditions on a value, prefer the `$on` proposition
over a nested `from`: `"where": {"$on": [{"gl_code": "1600"}, {<scope>}]}`
("output GIVEN scope"). On the flat table Aito hits the index directly
instead of materializing the subquery — ~50× faster (138 ms vs 7 s,
verified). `$patterns` still needs the nested `from` above; this trick is
for ordinary relate (e.g. rule diagnostics, ADR 0015).

**Gotchas:**
- `$related.k` defaults to 32 and is a focus cap, *not* a result limit
  — use the outer `limit` for row count.
- `$related`'s default `infoGain` mode surfaces anti-correlated
  candidates (large `fs.f`, but `fs.fOnCondition = 0` — match many rows,
  never the target). Gate on `fs.fOnCondition >= MIN_SUPPORT`, not on
  `fs.f`, to drop them along with rules too rare to trust.
- For a "what predicts X" rule list, keep only **positive** patterns:
  `lift > 1` (the conjunction makes X more likely than its base rate).
  `infoGain` re-emits every strong rule as a `lift ≈ 0` anti-pattern for
  each *other* target — drop those (`lift <= 1`).
- `$related.by` defaults to `infoGain` (keeps anti-correlations, good
  for classification). Use `lift` only for basket-affinity mining.
- Pattern mining is heavy (~9-11 s server-side at 128 k rows). Keep it
  on the precompute/warm-cache path, never in a synchronous request.

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
