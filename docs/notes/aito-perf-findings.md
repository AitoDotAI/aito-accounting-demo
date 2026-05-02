# Aito performance findings (May 2026)

Slow paths and API gaps surfaced while making the deployed demo
(accounting.aito.ai) fast enough for sales walkthroughs and credible
for a CTO read. Captured here so the core team can file/fix what's
worth fixing and so future iterations of this repo don't regress
around the workarounds.

**Flag summary (full detail below).** Sorted by impact on the demo:

| # | Issue | Repro impact | Workaround |
|---|---|---|---|
| 1 | `where: {linkedColumn: X}` expands all linked-entity fields as priors | 2.3 s vs 325 ms (7×) on `_recommend` | use explicit `linkedColumn.keyField: X` |
| 2 | First query against any table costs ~12 s of cold load | First user pays full table-load latency | startup warmup + precompute store |
| 3 | No documented row-delete API | `cache_entries` leaked 186 stale rows; precompute table accumulates dupes | none — reads use `limit:1`, so behaviour is correct but tables grow unbounded |
| 4 | Boolean column rejects truthy non-bool (`1`, `"true"`) | Caught us during a bisect; clear error | pass `True`/`False` exactly |
| 5 | `_search` `limit:0` count is ~1 s on cold table | `/api/help/stats` 2.1 s cold, 14 ms warm | included in startup warmup |
| 6 | Cache `set` has no upsert primitive | 2× round-trip per write (delete + insert) | combine with #3 — delete is 404 anyway, so we're effectively just inserting |

Items 1, 2, 4 are documented in detail in the original sections.
Items 3, 5, 6 are new flags from the May 2 deploy iteration —
captured below in §3.

---

## 1. `where: {linkedColumn: X}` shortcut expands all linked-entity fields as priors

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

A2 vs A3 narrowed it to the linked-Reference handling. The actual cause
(thanks @arau) is that `where: {prev_article_id: "LEGAL-00"}` is the
shortcut form: Aito materializes *every field* of the linked
`help_articles` row (title, body, category, tags, page_context,
customer_id) and uses them as recommendation priors. Traversing the
link explicitly to the *key* column avoids that expansion entirely:

| Variant | latency |
|---|---|
| `where: {prev_article_id: "LEGAL-00"}`           | **2272 ms** |
| `where: {prev_article_id.article_id: "LEGAL-00"}` |  **325 ms** |

Same hits, same data, ~7× faster. The `nullable: true` flag isn't the
underlying cause — `article_id` (non-null) wasn't slow because the
identity-traversal `article_id = X` matches non-null link keys without
expansion. `prev_article_id` (nullable) hit the property-expansion path.

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

Use the explicit-key traversal form so Aito does a plain key-match
instead of expanding linked-entity properties:

```http
POST /api/v1/_recommend
{
  "from": "help_impressions",
  "basedOn": [],
  "where": {
    "prev_article_id.article_id": "LEGAL-00",
    "customer_id": "CUST-0000",
    "article_id.customer_id": { "$or": ["*", "CUST-0000"] }
  },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}
```

(Empty `basedOn` skips prior-feature inference; not strictly required
once the property expansion is gone, but it's clean and slightly faster.)

### What we'd hope from core

The shortcut form is the natural way to express the filter. Two
options would make this trap less sharp:

- Make `where: {linkedCol: X}` evaluate as identity-on-key by default
  (current behavior of `where: {nonNullableLinkedCol: X}`), and have
  callers opt *in* to the property-expansion behavior when they want
  it.
- Or surface the expansion in error/explain output so applications
  notice it before profiling.

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

## 3. No documented row-delete API; cache tables accumulate dupes

### Symptom

`cache_entries` table on the deployed Aito had **321 rows for 135
distinct keys** — 186 stale duplicates accumulated over the demo's
lifetime. Same shape ready to happen on `precompute_entries`.

### Cause

`src/cache.py::set()` and `src/precompute_store.py::put()` both
implement upsert as delete-then-insert:

```python
client._request("POST", f"/data/{TABLE}/delete", json={
    "from": TABLE, "where": {"key": key}
})
client._request("POST", f"/data/{TABLE}", json={...})
```

The delete call returns **HTTP 404** —
`The requested table {TABLE}/delete does not exist`. The error is
swallowed by the surrounding try/except, every insert succeeds,
and a stale row is left behind on every write.

Verified the URL pattern doesn't exist with several variants:

```text
POST   /data/precompute_entries/delete       → 404
POST   /data/precompute_entries/_delete      → 404
POST   /_delete                               → 404
DELETE /data/precompute_entries (with body)  → 405 method not supported
```

No `$id` / `_id` / `$row` field is queryable in `_search select`,
so we can't even target individual rows for deletion. There's
also no internal row identifier we can use to build a delete
payload.

### Workaround

None on the read side — `precompute_store.get()` and `cache.get()`
both use `limit:1` and the row content is identical, so behaviour
is correct. But the tables grow without bound.

`data/dedupe_precompute_entries.py` is checked in but blocked on
the missing delete API. It currently runs in dry-run mode only.

### What we'd hope from core

- A documented row-delete REST endpoint, ideally `POST /data/{table}/_delete`
  with a `where` body identical to `_search`.
- Or a native upsert primitive — `POST /data/{table}` with an
  optional `upsertOn: ["key"]` shape — so the application doesn't
  need to manage delete-then-insert at all.

---

## 4. Boolean columns reject truthy non-bool values

### Symptom

While bisecting a separate slow path, tried passing `goal: {clicked: 1}`
and `goal: {clicked: "true"}` to `_recommend`. Both rejected with
clear errors:

```
"field 'clicked' of type Boolean cannot be '1' of type Int"
"field 'clicked' of type Boolean cannot be '"true"' of type String"
```

### Why it matters

This is correct, defensible behaviour — Aito's strict typing
caught us being sloppy. Worth flagging because some Python or JS
frameworks ship JSON payloads with `true` serialized as `1` /
`"true"` depending on the toolchain, and the failure mode is
*successful HTTP 400 with no hits*, not a silent slow path.

### What we'd hope from core

Nothing — strict typing is the right call. Just noting it.

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
