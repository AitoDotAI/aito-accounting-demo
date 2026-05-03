# Message to Aito core — May 2026

A consolidated read of everything we hit while making
accounting.aito.ai land for a CTO/CFO/InfoSec read at 1 M-row
scale. Sorted by user-visible impact. This is the doc to share
with whoever is closest to ingestion + query path internals.

The full bisects + repro bodies are in
`docs/notes/aito-perf-findings.md` §1–4. This note is the
shorter pitch, with the new things from yesterday's 1 M-scale
push tacked on at the end.

---

## What we'd most like fixed

### 1. Sustained heavy precompute traffic at 1 M scale collapses the instance

This is the new one. Symptoms:

- `./do precompute --workers 4` (or even `--workers 1`) running per-customer
  fan-out (`mine_rules` + `match_all` + `scan_all` +
  `compute_prediction_quality` + `compute_rule_performance`) for the demo's
  255 customers worked fine at `--medium` scale (128 k invoices total).
- At 1 M scale, after the first 4–7 customers, every subsequent call to
  Aito starts returning 504. Our circuit breaker opens. The next 10+
  customers get written as 23-KB stubs.
- Same pattern across three runs: workers=4, workers=2, workers=1.
- Backoff-retry (60/120/240 s, breaker reset between attempts) recovered
  one customer per run on average; the rest stayed stubs even after
  ~7 minutes of pause.
- A *single* `_search customers limit:1` against the 255-row customers
  table during this period takes 25–30 s. So Aito is alive — it's just
  process-wide degraded for a while after the precompute load lands.

Hypothesis: index updates / query planning fall behind under sustained
heavy multi-table read load on a freshly-loaded 1 M-row table.

What would help:
- Surface a queue-depth or backpressure metric we can poll, so the
  precompute can pace itself instead of hammering blind.
- Or, an explicit "heavy-batch mode" the client opts into so Aito knows
  to serialize internally rather than 504.
- Either way, a documented "what you can run concurrently against an
  N-row table" guidance would let demos/CTOs predict their PoC sizing.

### 2. Writes should use the jobs API; sync `POST /data/{table}` is brittle at scale

This was the user's point in feedback — the sync write path was the source
of two of the issues we hit:

- **`/data/{table}/batch`** times out client-side (httpx ReadTimeout,
  120 s) once the target table passes ~600 k rows. We replaced this with
  the file-upload + jobs flow (`POST /data/{table}/file` → S3 PUT
  gzipped NDJSON → `POST /data/{table}/file/{id}` trigger → poll
  `GET /data/{table}/file/{id}` until `phase: Finished`). 1 024 000
  invoices in 35 min vs days on `/batch`.
- **Cache write upserts** (`cache.set` and `precompute_store.put`)
  do delete-then-insert via `POST /data/{table}/delete` (404, see #5
  below). We don't have a documented async-jobs equivalent for
  individual-row writes, so the cache tables accumulate duplicates
  unbounded.

What would help:
- Make jobs the primary write path. Document `/data/{table}/file` +
  jobs as the recommended ingestion API; mark `/data/{table}/batch`
  as legacy / for tables under N rows.
- Add jobs-based primitives for: row delete (`POST /data/{table}/_delete-job`
  with a `where` body), upsert (`POST /data/{table}/_upsert-job` with
  an `upsertOn` key list), and batch update.
- Surface job status via `GET /jobs` and `GET /jobs/{id}` consistently
  (the file-upload jobs surface only via `GET /data/{table}/file/{id}`,
  while `/jobs` returns `[]`).

### 3. `where: {linkedColumn: X}` shortcut expands all linked-entity fields as priors

Already documented in `aito-perf-findings.md` §1. Repeating because it's
still the highest-impact fix in pure user-experience terms:

| variant | latency |
|---|---|
| `where: {prev_article_id: "LEGAL-00"}` (shortcut) | 2272 ms |
| `where: {prev_article_id.article_id: "LEGAL-00"}` (explicit key) | 325 ms |

Same hits, same data, **7× faster** with the explicit-key form. The
shortcut is the natural way to express the filter and is what most users
will write first.

Suggested fix: make `where: {linkedCol: X}` evaluate as identity-on-key
by default, and have callers opt *in* to the property-expansion behavior.

### 4. First query against a table costs ~12 s of cold load

`help_impressions` (14 k rows) takes 12.8 s on the first hit after
process restart, then drops to 14 ms. The deployed demo's first user
pays this cost; we worked around with a startup `_search limit:1`
warmup pass.

Suggested fix: a warm-on-deploy hook, or just faster lazy-load of small
tables. 14 k rows shouldn't take 12 s to become queryable.

### 5. `POST /data/{table}/delete` returns 404; row-delete API not at the documented-looking URL

Already in `aito-perf-findings.md` §3.

`cache_entries` table on the deployed instance had **321 rows for 135
distinct keys** — every `cache.set` since deploy has been leaking a
duplicate row because the delete leg of delete-then-insert silently
returns 404 and the insert goes through anyway.

Several variants tested, all 404 / 405:

```
POST   /data/cache_entries/delete     → 404
POST   /data/cache_entries/_delete    → 404
POST   /_delete                        → 404
DELETE /data/cache_entries (with body) → 405
```

Combine with #2 above: the right shape is probably an async
`_delete-job` with a `where` body.

### 6. `/data/{table}/optimize` defaults exceed our 120 s client cap on freshly-loaded large tables

Aito's optimize on a 1 M-row table immediately after bulk ingest hits
our 120 s timeout, the error gets swallowed by the loader's
best-effort try/except, and the table is left un-optimized. Downstream
symptom: `_search invoices limit:1` taking 25 s instead of 250 ms.

We patched our client to allow `timeout=None` for optimize. After 5–10
minutes of "settle time" the same call completes in 5.6 s — so the
issue is mostly that optimize blocks while the bulk-ingest jobs are
still rebuilding the index. Worth either making optimize wait for
those jobs to finish before starting, or making it idempotent so the
client can retry until success.

### 7. `/schema` endpoint hangs while `_search` works

When the instance is degraded (under heavy precompute load):

- `GET /schema` → 30 s+ timeout
- `POST /_search ... limit:1` against the same data → 25–30 s, returns 200

We had to switch our `check_connectivity` probe from `/schema` to a
tiny `_search` because the schema endpoint doesn't degrade gracefully.

Probably `/schema` is rebuilding a lot of in-memory state on every
call. Caching the schema or short-circuiting it from the same code path
that already serves `_search` would make a degraded instance still
feel reachable.

### 8. Boolean strict typing (informational, no fix needed)

`goal: {clicked: 1}` and `goal: {clicked: "true"}` are rejected with
clear error messages. This is correct typing behavior and we're flagging
only because some toolchains (JS Date.toJSON, Python dataclasses with
default_factory) ship payloads with truthy non-bools. Worth keeping the
strict behavior; just helpful for anyone bisecting.

---

## Recommended diagnostic priorities for core

1. **#1 (1 M-scale instance collapse under sustained reads).** Show-stopper for any CTO eval — without this fixed, Aito's "millions of rows" pitch can't survive a ~30-min PoC.
2. **#2 (jobs-based write API as the documented path).** Unlocks reliable production deploys at scale; eliminates four of the other issues by making them moot.
3. **#3 (linked-column where shortcut).** Cheap win, large user-experience improvement. The other Items 1+2 are infrastructural; this is a query-language clarification.

Items 4–8 are nice-to-have once 1–3 are in.

---

## What we built around the gaps (so nothing here is blocking us)

- Bulk file-upload loader (PR #11): replaces `/data/{table}/batch`.
  Worked fine for the 1 M ingest.
- Aito-backed precompute store (PR #7, #8): all read-path projections
  go through a single `precompute_entries` table, served via the same
  3-layer pattern (L1 → Aito → bootstrap JSON) so brief upstream
  outages degrade gracefully.
- Backoff-retry in precompute (PR #12): recovers one customer per
  failure pattern; doesn't outlast a sustained 1 M-scale degradation.
- `/healthz` endpoint + Azure keep-warm pinger (PR #6): avoids the
  10-second container cold-start that would otherwise compound any
  Aito flakiness.
- Live latency ticker (PR #12): per-op breakdown surfaces the demo's
  actual numbers in the corner of every page so a CTO read can verify
  the latency claim by clicking around for 30 seconds.

The ergonomics from the demo side are now good. The remaining headroom
is on the Aito core side.

---

## Concrete query bodies

For each finding above, the actual JSON we send. Copy-pasteable
against `https://shared.aito.ai/db/aito-accounting-demo/api/v1` after
`./do reset-data` from this repo's fixtures.

### Finding #1 — what one customer's precompute looks like

A single `precompute_one_customer` call issues these queries. Running
4–5 of these concurrently (workers≥2) at 1 M scale is what tipped
shared.aito.ai into the 504-storm.

```http
# From compute_prediction_quality — by far the heaviest. ~10–60s per customer
# at 1 M scale. Run for 7 customers ⇒ measured collapse.
POST /_evaluate
{
  "testSource": { "from": "invoices", "where": {"customer_id": "CUST-0000"}, "limit": 50 },
  "evaluate":   { "from": "invoices",
                  "where": {
                    "customer_id": "CUST-0000",
                    "vendor":   { "$get": "vendor" },
                    "amount":   { "$get": "amount" },
                    "category": { "$get": "category" }
                  },
                  "predict": "gl_code" }
}

# From rule mining — issued ~30× per customer (one per (field, value) pair
# we want to relate to gl_code). Each call ~250–800 ms at 1 M scale.
POST /_relate
{
  "from": "invoices",
  "where": { "vendor": "Kesko Oyj", "customer_id": "CUST-0000" },
  "relate": "gl_code"
}

# From invoice precompute — for each of 50 unrouted invoices, two _predicts
# fan out in parallel. So 100 _predict calls per customer, each 100–400 ms.
POST /_predict
{
  "from": "invoices",
  "where": { "customer_id": "CUST-0000",
             "vendor": "Kesko Oyj",
             "amount": 4220,
             "category": "supplies" },
  "predict": "gl_code",
  "select": [ "$p", "feature",
              { "$why": { "highlight": { "posPreTag": "<mark>", "posPostTag": "</mark>" } } } ]
}
POST /_predict   # same shape, predict: "approver"

# From matching — _match per bank transaction, 8 transactions.
POST /_match
{
  "from": "bank_transactions",
  "where": { "description": "KESKO OYJ", "amount": 4220, "customer_id": "CUST-0000" },
  "match": "invoice_id",
  "select": ["$p", "vendor", "invoice_id", "amount", "$why"],
  "limit": 5
}

# From anomaly scan + rule replay + quality overview: a few more _search /
# _predict calls per customer at similar shapes.
```

Total per customer: ~150–200 Aito calls. Per-call latency at 1 M scale
ranges 100 ms (warm) to 25 s (mid-collapse). Sustained for ~20 min.

### Finding #2 — current bulk upload (works) vs doc-suggested batch (doesn't)

**Works** (35 min for 1 024 000 rows):

```http
POST /data/invoices/file
{}
→ { "id": "abc-123", "url": "https://aitoai-customer-uploads.s3...PUT-presigned",
    "method": "PUT", "expires": "..." }

PUT https://aitoai-customer-uploads.s3.../   # gzipped NDJSON, 100k rows / chunk
Content-Type: application/octet-stream

POST /data/invoices/file/abc-123
{}
→ { "id": "abc-123", "status": "started" }

GET /data/invoices/file/abc-123     # poll until phase: Finished
→ { "status": { "phase": "Finished", "completedCount": 100000, ... } }
```

**Times out at scale** (`httpx.ReadTimeout` past ~600 k rows):

```http
POST /data/invoices/batch
[ { "invoice_id": "...", ... }, ... 1000 rows ]
```

**Silently 404s** (cache.set's delete-then-insert):

```http
POST /data/cache_entries/delete
{ "from": "cache_entries", "where": { "key": "help_search:CUST-0000:..." } }
→ 404 "The requested table cache_entries/delete does not exist"

# Then we insert anyway:
POST /data/cache_entries
{ "key": "help_search:CUST-0000:...", "value": "...", "created_at": ..., "ttl": 3600 }
→ 200 OK   ← row added; previous row never removed
```

What we'd want (suggested):

```http
POST /data/{table}/_delete-job
{ "from": "{table}", "where": { "key": "..." } }
→ { "id": "del-456", "status": "started" }

POST /data/{table}/_upsert-job
{ "rows": [ ... ], "upsertOn": ["key"] }
→ { "id": "upsert-789", "status": "started" }
```

### Finding #3 — linked-column shortcut vs explicit-key

```http
# 2272 ms — shortcut form, expands all 7 fields of help_articles as priors
POST /_recommend
{
  "from": "help_impressions",
  "where": { "prev_article_id": "LEGAL-00",   ←— shortcut
             "customer_id":      "CUST-0000" },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}

# 325 ms — explicit-key traversal, plain index lookup
POST /_recommend
{
  "from": "help_impressions",
  "where": { "prev_article_id.article_id": "LEGAL-00",   ←— explicit
             "customer_id": "CUST-0000" },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}
```

### Finding #4 — first-query cold load

The query is fine; it's the *first* call after process start that's slow.

```http
# 12.8 s on first hit, 14 ms after
POST /_recommend
{
  "from": "help_impressions",
  "where": { "customer_id": "CUST-0000", "page": "/invoices" },
  "recommend": "article_id",
  "goal": { "clicked": true },
  "limit": 5
}
```

### Finding #6 — optimize timing

```http
# Times out at our 120 s client cap immediately after a 1 M-row bulk
# ingest finishes. Same call completes in 5.6 s after ~5 min of settle.
POST /data/invoices/optimize
{}
```

### Finding #7 — `/schema` vs `_search` on a degraded instance

```http
# 30 s+ timeout when instance is under heavy precompute load
GET /schema

# 25–30 s but eventually returns 200 — same instance, same moment
POST /_search
{ "from": "customers", "limit": 1 }
```

We use the second form for our connectivity probe now. The first
should at minimum cache its result for N seconds so a degraded
instance still answers it quickly.

### Finding #8 — Boolean strict typing (info only)

```http
# These all 400 with clear errors
POST /_recommend
{ ..., "goal": { "clicked": 1 } }
→ "field 'clicked' of type Boolean cannot be '1' of type Int"

{ ..., "goal": { "clicked": "true" } }
→ "field 'clicked' of type Boolean cannot be '\"true\"' of type String"

# Only this works
{ ..., "goal": { "clicked": true } }
```

---

## Answers to core's three follow-up questions (May 3)

### Q1. Does `POST /jobs/data/invoices/optimize` after ingest avoid the 504 storm?

The endpoint works. Confirmed end-to-end:

```http
POST /api/v1/jobs/data/invoices/optimize
{}
→ 201  { "id": "fec32a21-...", "path": "data/invoices/optimize",
         "startedAt": "2026-05-03T09:23:36.452Z" }

GET /api/v1/jobs/fec32a21-...
→ 200  { ..., "startedAt": "...09:23:36.452Z",
              "finishedAt": "...09:23:41.857Z",   ← ~5 s
              "expiresAt":  "...09:38:41.857Z" }
```

After firing it on `invoices`, `bank_transactions`, `help_impressions`,
`overrides` and waiting 60 s, latencies on a previously-stubbed
customer dropped from 25 s+ to 250–280 ms warm:

```
invoices CUST-0010 limit=1 attempt 1: 7.16s 200    ← cold load
invoices CUST-0010 limit=1 attempt 2: 0.28s 200    ← warm
invoices CUST-0010 limit=1 attempt 3: 0.28s 200
```

Verdict: **jobs-based optimize is the right path**. Our existing
`data_loader.optimize_table()` uses the sync `POST /data/{table}/optimize`
which races the still-running ingestion jobs and times out at our
120 s client cap, leaving the table un-optimized. Switching to
`POST /jobs/data/{table}/optimize` + polling to `finishedAt` fixes
this and is what the core team should recommend in the documented
ingest path.

We haven't yet retried a full per-customer precompute on top of this
optimized state to confirm the 504 storm doesn't recur — that's a
many-hour run. The latency drop after the jobs-optimize matches what
we saw with the sync optimize (after the ingest race had cleared),
so the hypothesis stands: optimize-after-ingest is the missing
piece. Worth core re-running the full 1 M precompute with this
patch to verify.

### Q2. Does `POST /data/_delete` (with `{from, where}` body) actually delete?

**Short answer: no — neither the sync nor the jobs form actually removes
the row.** Tested empirically:

```http
# Sentinel insert
POST /api/v1/data/precompute_entries
{ "name": "__core_test_sentinel__", "payload": "{}", "computed_at": 1 }
→ 200 OK   ✓ row exists; verified via _search

# Variant A — /data/_delete (suggested in the question)
POST /api/v1/data/_delete
{ "from": "precompute_entries", "where": { "name": "__core_test_sentinel__" } }
→ 400 { "message": "No such table: cache_entries" }
   ↑ message refers to a different table; cryptic. Even when we send a
     valid table name, the body shape isn't the working one.

# Variant B — /data/{table}/_delete
POST /api/v1/data/precompute_entries/_delete
{ "from": "precompute_entries", "where": { "name": "__core_test_sentinel__" } }
→ 404 "The requested table precompute_entries/_delete does not exist"

# Variant C — original URL we'd been using
POST /api/v1/data/precompute_entries/delete
{ "from": "precompute_entries", "where": { "name": "__core_test_sentinel__" } }
→ 404 "The requested table precompute_entries/delete does not exist"

# Variant D — DELETE method
DELETE /api/v1/data/precompute_entries
{ "where": { "name": "__core_test_sentinel__" } }
→ 405 "HTTP method not supported. Supported: POST"

# Variant E — jobs-based, /jobs/data/{table}/_delete
POST /api/v1/jobs/data/precompute_entries/_delete
{ "from": "precompute_entries", "where": { "name": "__core_test_sentinel__" } }
→ 201 { "id": "...", "path": "data/precompute_entries/_delete",
        "startedAt": "..." }

GET /api/v1/jobs/{id}
→ 200 { "startedAt": "...", "finishedAt": "..." }   ← instant; no error reported

# Verify outcome
POST /api/v1/_search
{ "from": "precompute_entries",
  "where": { "name": "__core_test_sentinel__" }, "limit": 1 }
→ { "total": 1, "hits": [ ... sentinel still here ... ] }   ✗ NOT DELETED
```

We tried four body shape variants on Variant E — `{where}` only,
`{from, where}`, just `{name: ...}`, and `{parameters: {from, where}}`.
All return 201 immediately, finish in milliseconds, **no error**, and
**don't delete the row**. The jobs surface accepts the request, reports
success, and silently no-ops.

Implication: there is no working row-delete API on this Aito instance
that we can find. The cache_entries leak we documented (321 rows, 135
distinct keys, 186 stale duplicates) can't be fixed application-side
until core ships a working delete primitive — sync or jobs-based, your
call.

### Q3. Did we want property-expansion behavior, or just identity?

**Identity, only ever identity.** We were using
`where: {prev_article_id: "LEGAL-00"}` to mean *"filter
help_impressions to rows where the user's previous article was
LEGAL-00."* Pure key-equality. We never wanted Aito to treat the
linked entity's other fields as recommendation priors — that's the
side effect that took us 7× longer to find than it should have.

So the answer for the message is: please **default-flip**, not just
better diagnostics. The shortcut form should mean identity-on-key
(matching the user's mental model and matching `where: {nonLinkedCol: X}`
behavior), and we should opt *in* to property-expansion explicitly
when we want it — say a separate `$expandProperties: true` flag, or
keep it on `basedOn` only. Diagnostics-only would still require
us to recognise the issue and write the workaround; default-flip
makes the natural code path the right one.

Our final query in `src/help_service.py::related_articles` uses the
explicit-key traversal `prev_article_id.article_id: X` to get the
identity behavior. That works but it's odd-looking SQL-shape — most
developers will write the shortcut form first.
