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

**Confine the candidate domain to the rows that are actually eligible.**
A `_predict` on a link column ranks *every* row of the linked table that
passes the `where`. For payment matching the eligible set is the open
ledger — about 30 invoices — not the tenant's whole invoice history:

```json
"where": {
  "description": "RETAIL MANAGEMENT CONSULTING OY TUR / 16.06.25",
  "amount": 14772.29,
  "invoice_id.customer_id": "CUST-0007",
  "invoice_id.invoice_id": {"$or": ["CUST-0007-INV-000006", "..."]}
}
```

Without the second clause the true invoice competes with ~1970 rows that
were never outstanding, and a fixed `limit` truncates it away: measured on
CUST-0007, accuracy on payments quoting no reference number was 11/19
unscoped and 18/19 scoped. It also makes `$p` mean something — the same
match moves from 0.023 to 0.482 — because the probability is spread over
candidates that could actually be settled.

**Use the linked key (`invoice_id.invoice_id`), not the bare predict
target.** Both rank identically, but `$or` on the target itself returns
`invoice_id: null` on every hit after the first, with a 200 — so a client
reading the predicted field silently loses every candidate but one.

## Pattern: Coding a bank line with no invoice

**Query** — predict a field on the table you are already in, when there is
no link to traverse:

```json
{
  "from": "bank_transactions",
  "where": {
    "customer_id": "CUST-0000",
    "description": "KORTTIMAKSUT TILITYS  19.04.25",
    "amount": 4703.86,
    "amount_band": "medium"
  },
  "predict": "gl_code",
  "select": ["$value", "$p", "$why"]
}
```

**Send the band, not only the amount.** Aito conditions on a categorical
`amount_band`, not on a raw `Decimal`. Measured: without the band, the
same counterparty returns its most common code whatever the size —
`KORTTIMAKSUT TILITYS` came back `4100` at both €120 and €4800, where the
truth flips at the small/medium boundary. With it, €120 codes `4500` and
€4800 codes `4100`. Nothing errors either way, which is what makes it
worth an assertion in `aito-check`.

A corollary for fixture design: a rule whose threshold does not coincide
with a band boundary is **unlearnable**, and the model will fall back to
the majority code rather than fail. Ours put the threshold at the
boundary once that was measured.

**Reaching the linked table instead** — `fromJoin` predicts a column of
another table through the link:

```json
{
  "from": "bank_transactions",
  "fromJoin": {"table": "invoices", "base": "invoice_id",
               "target": "invoice_id", "as": "inv"},
  "where": {"customer_id": "CUST-0000", "description": "KARDEX FINLAND  Saaja"},
  "predict": "inv.gl_code"
}
```

Address the joined columns **through the alias** — `inv.gl_code`. A bare
`gl_code` returns `Field not found: gl_code`. Verified: 90% accuracy
predicting an invoice's GL code from a synthesised statement line on two
tenants, against baselines of 46% and 25%.

## Pattern: Rule mining with `_relate`

**Query:**
```json
{
  "from": "invoices",
  "where": { "vendor": "Kesko Oyj" },
  "relate": "gl_code"
}
```

**Response shape** (v1; on v2 collections `related` and `condition` come
back with bare values — see the `relate` row of the v1/v2 table below):
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

**Response hit.** Shown in the **v1** shape, which wraps every value in
`$has`. This project's tables are v2 collections, where the engine returns
values **bare** — measured on `invoices.vendor`, a multi-token `String`:

```json
{ "related": { "vendor": "Europress Group Oy" },
  "condition": { "customer_id": "CUST-0007" } }
```

The `$has` that application code sees comes from `AitoV2Client.relate`
(`src/aito_v2_client.py`), which re-wraps v2's bare values into the v1
shape so existing callers keep working. It is **ours, not the engine's**.

**Do not copy a returned proposition into a `where`.** It reads as
copy-pasteable and the v1 shape invites it, but `$has` on a text column is
being narrowed to mean exactly one analyzed token, so a multi-token
`$has` becomes an error rather than a filter. Unwrap to a bare value
first — which is what `rulemining_service.parse_conjunction` does, and why
rule replay was unaffected:

```python
value = pred.get("$has") if isinstance(pred, dict) else pred
```

The original example, in v1 shape:
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

---

## v2 API (`/api/v2`) — what changes

The v2 API is not a version bump; see ADR 0017. Everything above is v1 and
still runs the live demo. This section is the delta, all verified live against
the `v2-demo` environment (core rev `7d5c48a9`).

**Addressing.** An environment is two path segments, `/env/<name>/`:

```
https://shared.aito.ai/db/aito-accounting-demo/env/v2-demo/api/v2/_query
```

The master API key authorizes every env — env auth is database-scoped and
there is no env-scoped key. Env names may **not** start with `_`, `env.`, or
`release.`; those prefixes are reserved (the built-in master env is
nonetheless reported as `env.master`).

**One endpoint, mostly.** `POST /api/v2/_query` takes the query type as a
top-level key. The grammar, per the server's own parse error:

```
from, let, where, search, get, predict, recommend, goal, relate, basedOn,
orderBy, select, offset, exclusiveness, limit, config, fromWhere, fromLimit,
relatePatterns, fromJoin, fromUnion
```

`_match` and `_evaluate` are **not** in it and remain separate endpoints
(`POST /api/v2/_match`, `POST /api/v2/_evaluate`). `recommend` answers both at
`/_query` and at `/_recommend`.

**Response deltas** (what actually breaks a v1 client):

| Verb | v1 | v2 |
|---|---|---|
| `predict` | value in `feature` | value in `$value` |
| `recommend` | column at top level (`article_id`) | `$value` (+ `select`ed columns) |
| `relate` | `related: {f: {$has: v}}` | `related: {f: v}` — bare, verified |
| `_evaluate` | metrics at top level | wrapped in `{"kind","data"}`; cases use `$value` |
| links | explicit | auto-flatten to dotted fields (`customer_id.name`) |

`$why` is unchanged — the same nested factor tree, so explanation parsing
carries over as-is.

`src/aito_v2_client.py` normalizes each of these, which is why the services
take either client unchanged.

### v2 gotchas that cost real time

- **`select: ["feature"]` used to 400.** As of rev `38a234a6` (2026-08-31)
  `feature` and `field` are accepted as v1 compat aliases on any ranked-value
  query, alongside `$value`. Prefer `$value` in new code.
- **`predict` returns ~10 candidates by default.** Pass `limit` to cover a
  target field's full value set, or alternatives silently go missing.
- **`relate`/`$patterns` need a *collection*.** A legacy (v1-uploaded) table
  returns **501 "supported on collections only"**.
- **`_match` was not usable for matching before rev `38a234a6`** — it returned
  `$f` (a raw count), never `$p`/`$why`, silently ignored `select`, and tied
  every candidate at 0 for unseen input (core issue V2-12). **Fixed
  2026-08-31**: it now returns a graded `$p`, generalizes to evidence never
  seen verbatim, and honours `select` / `$why`. (This demo's payment matching
  uses `_predict` on the linked `bank_transactions.invoice_id`, not `_match`.)
- **`_match` and `_predict` are the same computation on a linked column.**
  Measured 2026-09-16 on shared 2.9.0: the same `where` sent to
  `POST /_match` with `"match": "invoice_id"` and to `POST /_predict` with
  `"predict": "invoice_id"` returned byte-identical hits — same `$p` to six
  decimal places, same ordering. The "Payment matching with `_match`" pattern
  above is not a second capability; do not reach for `_match` expecting it to
  match where `_predict` could not.
- **A linked path in a `where` is a FILTER, not evidence — even inside
  `_predict`.** `invoice_id.customer_id` scopes the candidate domain, which is
  the tenant boundary payment matching relies on. Since 2.9.0 that filter is
  exact, case-sensitive equality, and that applies in inference queries too.
  Measured on a `_predict` whose target is `invoice_id`:

  ```
  invoice_id.vendor "Restaurant Kimito-Oskar Ab"  -> 5 hits, all that vendor
  invoice_id.vendor "RESTAURANT KIMITO-OSKAR AB"  -> 0 hits   (case)
  invoice_id.vendor "Restaurant Kimito-Oskar"     -> 0 hits   (partial)
  invoice_id.vendor "Episto Oy"  (not stored)     -> 0 hits
  ```

  So a linked column cannot carry fuzzy vendor evidence. Resolve the value
  first (`_predict vendor_name`), then filter on what that returns — a stored
  value — rather than on a raw bank string.
- **`recommend` silently dropped disjunctive filters on linked fields** before
  rev `38a234a6`: plain equality was honored but `{"$or": [...]}` and `$in`
  were discarded **with a 200**, leaking other tenants' rows through a
  multi-tenant eligibility clause (core issue V2-13). **Fixed 2026-08-31** —
  `$or` and `$in` on a linked field now filter correctly. Worth keeping in mind
  as a *shape* to test for: a dropped filter fails open, with a 200 and no
  error, so nothing but a row count catches it.
- **Bulk load then `optimize`.** `POST /data/{name}/optimize` after a batch
  load; predict is degraded until it runs (`relate` is already correct).
