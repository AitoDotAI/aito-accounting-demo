# Aito performance findings (May 2026)

Two slow paths surfaced while making the deployed demo (accounting.aito.ai)
fast enough for sales walkthroughs. Captured here so the core team can
file/fix what's worth fixing and so future iterations of this repo don't
regress around the workarounds.

---

## 1. `where` on a nullable linked Reference is ~7× slower than equivalent shapes

### Symptom

The "users who read this also read" call (`_recommend` over
`help_impressions`) was 2.3 s warm / 5–12 s cold. The slow factor was
the `where` filter, not the recommend itself.

### Repro

Same dataset (14,630 impressions), same recommend, same goal, only the
`where` column changes:

| Variant | latency (warm, 2nd-best of 4) | hits |
|---|---|---|
| A1 — `where: {customer_id, page}`             |  **323 ms** | 5 |
| A2 — `where: {customer_id, prev_article_id}`  | **2272 ms** | 5 |
| A3 — `where: {customer_id, article_id}`       |  **297 ms** | 1 |
| B1 — `where: {prev_article_id}`               | **2180 ms** | 5 |
| B2 — `where: {prev_article_id}` + `basedOn:[]` | **1081 ms** | 5 |

`_search` baseline with the same `where` shapes is fast across the board
(~230 ms each), so the slowdown is on the `_recommend` side.

A2 vs A3 isolates the cause: same column type (linked String → `help_articles.article_id`),
same recommend body, same dataset, same actual hits. The only difference
is the column's `nullable` flag.

### Schema (target column highlighted)

```json
{
  "table": "help_impressions",
  "columns": {
    "article_id":      { "type": "String",  "link": "help_articles.article_id", "nullable": false },
    "prev_article_id": { "type": "String",  "link": "help_articles.article_id", "nullable": true  },  // ← slow path when used in `where`
    "customer_id":     { "type": "String",  "nullable": false },
    "page":            { "type": "String",  "nullable": false },
    "clicked":         { "type": "Boolean", "nullable": false },
    "impression_id":   { "type": "String",  "nullable": false },
    "query":           { "type": "Text",    "analyzer": "english", "nullable": true },
    "timestamp":       { "type": "Int",     "nullable": false }
  }
}
```

Distribution: 14,630 rows total, 65 with `prev_article_id = "LEGAL-00"`.

### Slow query (the original)

```http
POST /api/v1/_recommend
{
  "from": "help_impressions",
  "where": {
    "prev_article_id": "LEGAL-00",
    "customer_id": "CUST-0000",
    "article_id.customer_id": { "$or": ["*", "CUST-0000"] }
  },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}
```

### Workaround

Don't filter on `prev_article_id`. Move the "currently viewing this article"
context out of `where` and use the eligibility traversal as the candidate
restriction. Same hits, ~7× faster:

```http
POST /api/v1/_recommend
{
  "from": "help_impressions",
  "basedOn": [],
  "where": {
    "article_id.customer_id": { "$or": ["*", "CUST-0000"] }
  },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}
```

(Empty `basedOn` skips prior-feature inference, which doesn't add
information when the eligibility-restricted candidate pool is small. Tip
from @arau.)

### What we'd hope from core

The same `_recommend` shape with `where: {customer_id, article_id}` is
~300 ms. Only `prev_article_id` (same type, same link target, just
`nullable: true`) trips a ~7× slower path. Fixing this would let
applications express "previous item" filters naturally without paying
for the workaround.

---

## 2. First query against a table costs ~12 s of cold load

### Symptom

The first request against `help_impressions` after deploy / instance
restart takes 12.8 s. Subsequent requests are sub-300 ms.

### Repro

```text
endpoint                                     warm   cold
/api/help/search                              14ms 12787ms   ← first hit pays the cold cost
/api/help/related                             15ms    29ms   ← served from precomputed JSON, doesn't touch Aito
/api/help/stats                               14ms  2129ms   ← second request to the same table; cold-load already underway
```

`/api/help/stats` does two `_search ... limit:0` count queries; warm it's
14 ms, but if it's the *first* hit on the table it's 2 s+. Same shape on
already-warm tables (`/api/customers`, `/api/invoices/pending`) is 14–293 ms.

### Workaround in this repo

`src/app.py` fires a single cheap `_search` against `help_impressions`
during the existing background warmup so the first real user doesn't
pay the cold-load cost. Belt-and-suspenders against the deployed
demo's "first impression" feel.

### What we'd hope from core

A warm-on-deploy hook, or simply faster lazy-load of small tables.
14k rows shouldn't take 12 s to become queryable.

---

## How this repo uses the findings

- `src/help_service.py::related_articles` uses the workaround query
  shape. A comment there points back to this note so the next reader
  knows why we don't filter on `prev_article_id`.
- `book/test_07_help.py::test_help_related_articles_query` snapshots
  the exact query JSON so a regression to the slow shape would show
  up in `./do book`.
- `src/app.py` warmup hits `help_impressions` and `customers` once
  on startup; that's enough to take the cold-load cost off the first
  user's path.
- `data/precomputed/help_related.json` ships precomputed
  related-articles for the demo's most-visited customers, so even
  if Aito hiccups, the help drawer's "users who read this also read"
  responds in ~10 ms.

---

## Endpoint perf snapshot (local Aito, 2026-05-01)

| endpoint                                  | warm   | cold     | how |
|---|---|---|---|
| `/api/multitenancy/landing`               |  15 ms |    29 ms | precomputed JSON |
| `/api/multitenancy/shared_vendors`        |  15 ms |   578 ms | fixture scan, in-process cached |
| `/api/customers`                          | 293 ms |   322 ms | live `_search` (worth caching) |
| `/api/help/search`                        |  14 ms | 12787 ms | live `_recommend`; cold-load dominates |
| `/api/help/related`                       |  15 ms |    29 ms | precomputed JSON, live fallback |
| `/api/help/stats`                         |  14 ms |  2129 ms | two live `_search`; benefits from warmup |
| `/api/invoices/pending`                   |  27 ms |    43 ms | precomputed JSON |
| `/api/matching/pairs`                     |  16 ms |    16 ms | precomputed JSON |
| `/api/anomalies/scan`                     |  14 ms |    14 ms | precomputed JSON |
| `/api/quality/*`                          |  14 ms |    25 ms | precomputed JSON |
| `/api/formfill/templates`                 |  14 ms |    22 ms | in-process cache, live fan-out |
| `/api/formfill/vendors`                   |  18 ms |    19 ms | precomputed JSON |

The pattern: anything that touches Aito live the *first time* eats the
cold-load cost. Anything served from `data/precomputed/` is sub-30 ms.
