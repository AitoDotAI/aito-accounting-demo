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
| 7 | `httpx.request(...)` per call repeats TLS handshake every request | ~110 ms steady-state vs ~280 ms per call (~3× faster after fix) | Pooled `httpx.Client` held on `AitoClient` instance |
| 8 | `_predict` with `$why` varies 0.44 s – 6.6 s **for the same query**, server-side — daytime only, and not caused by our own concurrency | the first click on a matching row felt broken at ~4 s | prefetch after render; compare settings with `X-Aito-Ms`, but record wall time too — above 2 calls in flight the header under-reports the wait |

Items 1, 2, 4 are documented in detail in the original sections.
Items 3, 5, 6 are new flags from the May 2 deploy iteration —
captured below in §3. Item 7 (May 2026) is documented in §4.
Item 8 (October 2026) is documented in §8, together with the claim it
disproves.

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

## 4. `httpx.request(...)` per call repeats TLS handshake every request

### Symptom

Every `_recommend` / `_search` / `_predict` call paid 200-300 ms of
"network overhead" on top of Aito's server-side time. Same code path
on a shared instance, same payloads, same client process — the
overhead repeated per call.

### Diagnosis

Aito returns its server-side execution time in the
`x-aitoai-response-time` response header. Splitting client wall-clock
against that header isolated the network/proxy cost cleanly:

```
requests.post() — fresh connection each call:
  #1: client=1533ms  server=1300ms  net=232ms
  #2: client=219ms   server=37ms    net=182ms
  #3: client=196ms   server=36ms    net=160ms

requests.Session() — pooled keep-alive connection:
  #1: client=249ms   server=38ms    net=211ms   ← TLS handshake
  #2: client=99ms    server=42ms    net=57ms    ← pooled
  #3: client=92ms    server=35ms    net=57ms
```

Pooled connection ⇒ network overhead drops from ~200 ms to **~57 ms**
(pure RTT). The 150 ms difference is the TLS handshake, paid once on
the first call and then never again.

`src/aito_client.py` was using `httpx.request(...)` — a top-level
helper that opens a fresh `httpx.Client` (and a fresh TCP+TLS
connection) per call. Every call paid the handshake.

### Workaround

Hold a single `httpx.Client` on the `AitoClient` instance and use
its `.request(...)` method. Per-call `timeout` override still works.
The circuit-breaker, retry, and per-path semaphore around the call
are unchanged.

```python
class AitoClient:
    def __init__(self, config):
        # ...existing fields...
        self._client = httpx.Client(headers=self._headers)

    def _request(self, method, path, json=None, timeout=120.0):
        # ...breaker / retry / semaphore unchanged...
        response = self._client.request(
            method, self._url(path), json=json, timeout=timeout,
        )
```

Measured against the live shared Aito instance after the fix:
~280 ms client-side per call → **~110 ms steady-state** (~3× faster,
identical request payloads).

### Cross-demo applicability

Same bug existed in `aito-erp-demo/src/aito_client.py` and
`aito-ecommerce-demo/src/aito_client.py`; both fixed in parallel
PRs. `aito-demo` (JS) is fine — `fetch()` in modern Node pools via
the global undici agent.

### What we'd hope from core

Nothing API-side — this is purely a client-side fix. But the official
Python SDK (when it exists) should default to a pooled client, and
the docs' Python examples should not show `httpx.request(...)` per
call.

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

---

## 8. Aito's own response time is the variance, and it is wide (Oct 2026)

### The claim under test

While making payment matching explain only the expanded row
(td-20260909115133919692), the same `_predict` with `$why` looked about
three times slower inside the running app (~3.3 s) than from a script
(~1.2 s) on the same tenant. A 3× on every live call would matter more
than any single view, so it was raised as td-20261030214404054563.

**It does not reproduce. The app is not the variable.**

### What made the first measurements misleading

They were taken minutes apart, one setting at a time, against a shared
instance. On this query that is not good enough: Aito's own server time
for the *same body* swings between 0.44 s and 6.6 s.

Nine distinct explain bodies, each asked twice back to back from one
script (`x-aitoai-response-time`, so no client overhead is included):

| ask | median | range |
|---|---|---|
| first  | 1001 ms | 444 – 3514 ms |
| second |  749 ms | 555 – 3280 ms |

The slowest single measurement in the set is a *second* ask of a body
whose first ask took 1620 ms. So "new query" does not explain it either.

### The paired test

Same explain, through the app and from a script, interleaved, alternating
which goes first, a fresh tenant per pair so no cache serves a repeat.
Comparing Aito's server time on both sides (`X-Aito-Ms` from the app,
`x-aitoai-response-time` from the script):

| | median | values |
|---|---|---|
| script | 3621 ms | 4399, 6585, 893, 4316, 1172, 4369, 1190, 3621, 832 |
| app    | 1036 ms | 823, 1175, 673, 1164, 1236, 791, 1036, 1254, 544 |

n = 9 pairs. App minus script: median **−2367 ms**; the app was slower in
**1 of 9**. If anything the script side drew the outliers — every pair
where the app went first left the script's identical call measuring
3.6 s or worse, which is worth its own look.

### What the app does cost

Small and stable. Each `/api/matching/explain` is `_search` 13–66 ms (the
cache read) plus one `_predict`, and end to end the app adds roughly
100–350 ms around Aito's time: two cache round trips (`get` ~61 ms, `set`
~107 ms, measured against the L2 table), FastAPI, and serialisation. Of a
3.65 s first open, instrumented: 3.43 s the `_predict`, 0.07 s cache
reads, 0.15 s the cache write, 4 ms everything else.

### How to measure this here, so the next person does not redo it

- `AitoV2Client._request` already reads `x-aitoai-response-time`, and
  `src/app.py` exposes the per-request sum as `X-Aito-Ms`, the count as
  `X-Aito-Calls` and the breakdown as `X-Aito-Ops`
  (`_search:16.7,_predict:1139.7`). Use those. Wall clock on a shared
  instance cannot tell a slow client from a busy server.
- Compare settings **paired and interleaved**, alternating order, not one
  batch after the other. Unpaired samples minutes apart are how a 3×
  that is not there gets reported — by me, in this case.
- Nine pairs was enough to invert the sign of the result. Fewer would not
  have been: at n=5 the same test read −35 ms with the app slower in 2.

### What to do about the real finding

The demo-visible consequence is that a cold explanation can take four
seconds. That is handled where the user meets it: the matching page
prefetches each row's explanation once the list has rendered, so nobody
waits on the first call, and our cache makes a reopen 3 ms.

The width itself — 0.44 s to 6.6 s for one query class on a warm table —
is an Aito-side question, not an app one, and belongs with the core team
alongside flag 2 (cold load).

### The width is not our own concurrency, and it is not there at night

Measured 2026-10-30, 23:00–23:08, same query class
(`matching_service.ranking_query(..., explain=True)`), to answer the
obvious suspicion: that we cause the tail ourselves by asking several
things at once. We do not.

Quiet hours, one query in flight, ≤1 qps, five fresh tenants, 30 bodies
each asked twice:

| n | median | p90 | max | over 2 s |
|---|---|---|---|---|
| 60 | 603 ms | 1077 ms | 1247 ms | 0 |

Against the daytime table above (first-ask median 1001 ms, 444–3514 ms),
the median is ~40% faster at night and the multi-second tail is gone
entirely. Then the same bodies driven at 1, 2 and 4 of our own queries in
flight, 45–120 s per step:

| in flight | aito p50 | p90 | max | wall p50 | wall max |
|---|---|---|---|---|---|
| 1 | 612 ms | 1086 ms | 1259 ms | 749 ms | 1429 ms |
| 2 | 1174 ms | 1632 ms | 1917 ms | 1356 ms | 2202 ms |
| 4 | 1225 ms | 1702 ms | 1948 ms | 2487 ms | 5115 ms |

Across 401 queries that night the worst single server-side time was
**1948 ms**. Our own concurrency cannot produce the 3.5–6.6 s times, so
the width tracks time of day — load from elsewhere on the shared
instance. Written down beforehand, the prediction was that 4 in flight
would reproduce the tail; it did not.

Two things the concurrency numbers do say:

- The cost of asking at all is paid once, between 1 and 2 in flight
  (612 → 1174 ms). Going on to 4 adds 51 ms to the engine's own time.
- Past 2 in flight the engine's reported time stops growing and the
  waiting moves into wall time: wall minus `x-aitoai-response-time` is
  134 ms at 1 in flight, 178 ms at 2, and 1157 ms at 4 (max 3805 ms).
  So roughly two effective slots for this query class, with the queue
  ahead of them not counted in the header. Caveat: the probe is a
  4-thread Python client parsing ~75 KiB responses, so GIL contention
  may own part of that gap — read 1157 ms as an upper bound on the
  server's share, not a measurement of it.

Which sharpens the measurement advice above: `X-Aito-Ms` is the right
number for comparing two settings, and the wrong number for asking what
a page costs a user. Above two concurrent calls it under-reports the
wait by about a second. Record both.

Where this leaves the app: payment matching is sequential and has to be
— each payment removes its invoice from the candidate set the next one
is ranked against — so it never has more than one call in flight, and
the row prefetch is a serial chain after render. The fan-out in this
repo is smart form fill (up to 7 fields at once, `formfill_service.py`)
and the startup warmup (`app.py`), both held to `AITO_INFLIGHT_LIMIT`
(default 4) by the process-wide semaphore in `src/aito_client.py`. That
default is the only lever these numbers argue about.
