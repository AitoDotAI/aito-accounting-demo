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
