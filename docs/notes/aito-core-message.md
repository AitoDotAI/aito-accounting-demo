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

## Net asks for core (after the May 3 verification round)

Two real bugs:

1. **`POST /jobs/data/{table}/_delete` silent failure.** Returns 201
   with a job id and `finishedAt` timestamp on `/jobs/{id}`, but
   `/jobs/{id}/result` returns 500 and the row stays. Either reject
   at submit with a clear 400 or wire to the working
   `/jobs/data/_delete` handler. (§5b)
2. **`GET /jobs/{id}` doesn't surface job errors.** Only
   `/jobs/{id}/result` reveals failures; the status endpoint shows
   only `finishedAt` whether the job succeeded or 500'd. This is
   what hid bug #1 from us. (§5c)

Two doc/discoverability fixes:

3. **Document `POST /api/v1/data/_delete`.** Working endpoint, but
   undocumented; every reasonable URL guess
   (`/data/{table}/delete`, `/data/{table}/_delete`,
   `DELETE /data/{table}`) returns 404/405 with misleading "table
   not found" errors when the table exists. (§5a)
4. **Document the gzipped file-upload + jobs flow as the primary
   ingest path.** `/data/{table}/batch` times out past ~600 k rows;
   the file-upload flow took 1 024 000 invoices in 35 min. The gzip
   requirement is non-obvious — uncompressed payloads silently
   fail with `Unknown exception` per row. (§2)

Already merged to Aito core main, shipping next deploy:

5. **Upsert primitive.** Lets `cache.set()` and
   `precompute_store.put()` be one call instead of delete-then-insert
   pair. Eliminates the cache_entries leak class entirely.

Open performance question (worth investigating, not a blocker):

6. **Sustained heavy precompute reads at 1 M scale produce a 504
   storm even after jobs-based optimize.** Verified empirically May 3:
   re-ran top-20 precompute on a freshly jobs-optimized state and
   got 2 ok / 2 partial / 16 stub — same collapse pattern. Optimize
   is necessary (drops `_search` from 25 s to 280 ms) but not
   sufficient. There's a residual concurrency or load-handling
   issue separate from un-optimized indexes. (§1, Q1)

Appendix-quality observations:

- 12 s cold-load on first query against any table (§4)
- `/schema` hangs on degraded instance while `_search` answers (§7)
- Boolean strict typing — informational, no fix needed (§8)

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

### 2. Bulk ingest path: jobs flow works but isn't documented as the recommended path

`/data/{table}/batch` times out client-side (httpx ReadTimeout, 120 s)
once the target table passes ~600 k rows. We replaced it with the
file-upload + jobs flow:

```
POST /data/{table}/file              → presigned S3 PUT URL + ingest ID
PUT  s3://...                         (gzipped NDJSON; chunked at 100 k rows)
POST /data/{table}/file/{id}         → triggers ingestion
GET  /data/{table}/file/{id}         → poll until phase: Finished
```

1 024 000 invoices in 35 min vs days on `/batch`. Two non-obvious
gotchas worth pinning in the docs:

- The body **must be gzipped**. Uncompressed NDJSON silently fails
  with `Unknown exception` per row, no hint that compression is
  required.
- The `format` parameter in the init body is ignored; only the gzip
  wrapping matters.

We'd ask core to make jobs-style ingest the documented primary path
and demote `/data/{table}/batch` to "legacy / small tables only."

(Original framing of this section called for jobs-based row writes
in general. After core's clarification, the row-write story is in
better shape than we thought — `/data/_delete` works synchronously
and the upsert primitive is en route. See §5 for the residual asks.)

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

### 5. Row-delete: working endpoint is undocumented; one jobs form is broken

**Correction from the original message — we initially concluded "no
working delete API." That's wrong; we missed it.** The working URL is
`POST /api/v1/data/_delete` with `{from, where}` body — the table goes
in the body, not the path. We discovered this only after core flagged
it. Verified working end-to-end now:

```http
POST /api/v1/data/_delete
{ "from": "precompute_entries",
  "where": { "name": "__verify_delete_works__" } }
→ 200 { "total": 1 }    ✓ row gone
```

The actual problems we'd ask core to fix:

**5a — Documentation gap.** Every reasonable URL guess returns 404 or
405:

```
POST   /data/{table}/delete           → 404 "table {table}/delete does not exist"
POST   /data/{table}/_delete          → 404 "table {table}/_delete does not exist"
POST   /_delete                        → 404 "path /_delete does not exist"
DELETE /data/{table}                   → 405 "method not supported"
```

The error messages actively mislead — they say "table not found"
when the table exists but the URL is wrong. We spent two debug
cycles concluding the endpoint didn't exist before core flagged the
correct URL. A docs pointer + better error message ("did you mean
POST /data/_delete?") would prevent this for the next person.

**5b — Real bug.** `POST /api/v1/jobs/data/{table}/_delete`
(table-in-URL form) accepts the request, marks the job
`finishedAt`, and silently no-ops. The row is not deleted.
Reproduced just now:

```http
POST /api/v1/jobs/data/precompute_entries/_delete
{ "from": "precompute_entries", "where": { "name": "__broken_jobs_url__" } }
→ 201 { "id": "...", "path": "data/precompute_entries/_delete",
        "startedAt": "..." }

GET /api/v1/jobs/{id}             ← what we polled before
→ 200 { ..., "finishedAt": "...", ... }      ← LOOKS LIKE SUCCESS

GET /api/v1/jobs/{id}/result      ← what we should have polled
→ 500 "There was an internal server error."  ← actual outcome

POST /api/v1/_search { ..., "where": { "name": "__broken_jobs_url__" } }
→ { "total": 1 }                              ← row stays
```

The non-table-in-URL form `POST /api/v1/jobs/data/_delete` works
correctly (201 → `/jobs/{id}/result` returns 200 with delete count).
Either reject the table-in-URL form at submit time with a clear 400,
or wire it up to the same handler.

**5c — Discoverability.** `GET /jobs/{id}` shows `finishedAt` even
when the job actually errored; the error is only surfaced at
`/jobs/{id}/result`. That's what hid 5b from us — we polled
`/jobs/{id}`, saw `finishedAt`, and concluded success. Surfacing
"finished but errored" in the status response would have caught
this immediately.

**5d — Upsert primitive.** Even with `/data/_delete` working,
delete-then-insert is two round-trips per cache write. A native
`POST /api/v1/data/{table}` with `{rows: [...], upsertOn: ["key"]}`
would let `cache.set()` and `precompute_store.put()` be one call.
Per @arau, this is merged to Aito core's main and ships next deploy.

**Application-side fix shipped.** `cache.py` and `precompute_store.py`
both switched from `/data/{table}/delete` (404, silent leak) to
`/data/_delete` (200, actually works). Cache leak is now self-healing
on next process write per key.

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

**Update (May 3 evening):** re-ran the full top-20 precompute on top
of the jobs-optimized state. Result: **2 ok / 2 partial / 16 stub** —
same collapse pattern as before. The breaker opens after ~2 successful
customers and the rest fail-fast.

So jobs-based optimize is the right path *and* fixes the post-ingest
slowness, but it is **not sufficient on its own** to prevent the 504
storm under sustained per-customer fan-out at 1 M scale. There's a
residual concurrency or load-handling issue separate from
un-optimized indexes. This is the open performance question for core
to investigate (item 6 in the *Net asks* summary at the top).

### Q2. Does `POST /data/_delete` (with `{from, where}` body) actually delete?

**Yes — we missed it on the first pass.** Core's verdict caught two
things: (1) we had a bad initial probe (the 400 we logged in the
original message wasn't reproducible against `precompute_entries` and
either had a typo or was transient), and (2) we polled the wrong URL
to check job outcome. Re-verified end-to-end:

```http
# Working: /data/_delete with `from` in the body
POST /api/v1/data/_delete
{ "from": "precompute_entries",
  "where": { "name": "__verify_delete_works__" } }
→ 200 { "total": 1 }    ✓ row gone
```

We polled `GET /jobs/{id}` (status only) on the jobs-based variants;
the right poll URL is `GET /jobs/{id}/result`. With that:

```http
POST /api/v1/jobs/data/_delete                     ← no table in URL
{ "from": "precompute_entries", "where": { "name": "..." } }
→ 201 { "id": "..." }
GET  /api/v1/jobs/{id}/result    → 200 { "total": 1 }    ✓ row gone

POST /api/v1/jobs/data/{table}/_delete             ← table in URL
{ ... }
→ 201 { "id": "...", "path": "data/{table}/_delete" }
GET  /api/v1/jobs/{id}           → 200 { "finishedAt": "..." }  (looked like success)
GET  /api/v1/jobs/{id}/result    → 500 "internal server error"   ✗ row stays
```

So the application-side verdict is: the cache leak fix is a one-line
URL change. **Switched `cache.set()` and `precompute_store.put()` from
`/data/{table}/delete` (404) to `/data/_delete` (200).** Cache leak is
now self-healing on next process write per key.

The asks we'd push back to core (now in §5):

- **5a — docs:** `/data/_delete` is the working endpoint but isn't in
  any obvious place we could find. Every reasonable URL guess returns
  404/405 with misleading "table not found" errors when the table
  exists. We spent two debug cycles concluding it didn't exist.
- **5b — bug:** the table-in-URL jobs form
  `POST /jobs/data/{table}/_delete` returns 201, marks the job
  finished, and silently no-ops. `/jobs/{id}/result` reveals the 500;
  `/jobs/{id}` doesn't.
- **5c — discoverability:** `/jobs/{id}` should reflect that the job
  errored instead of looking like a clean `finishedAt`. That's what
  hid 5b from us originally.
- **5d — upsert:** even with `/data/_delete` working, delete-then-insert
  is two round-trips per cache write. A native upsert primitive
  (`{rows, upsertOn}`) would let `cache.set()` be one call. Per @arau
  this is merged to Aito core's main and ships next deploy.

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
