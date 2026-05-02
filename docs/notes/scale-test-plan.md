# 1 M-invoice scale test plan

The deployed demo currently runs against `--medium` fixtures (128 k
total invoices, top customer = CUST-0000 at 16 k). To make the demo
credible to a CTO read, the next push is the `full` scale: ~1 M
total, top customer at 128 k.

This note is the runbook + checkpoints. Execution is the user's
call; the load + precompute take hours and should run when there's
a maintenance window for the deployed instance.

---

## Tier shapes

| scale | top tier | bottom tier | total | use |
|---|---|---|---|---|
| `--small`  |     2 000 inv |   16 inv |     ~10 k | dev iteration |
| `--medium` |    16 000 inv |  125 inv |    128 k | currently deployed |
| (default)  |   128 000 inv | 1 000 inv | **1 024 k** | this plan |

`data/generate_fixtures.py:420` defines the tier table — geometric
distribution, 256 customers, same shapes across scales (only
counts change).

## Sequence

```
1. generate_fixtures (~5 min)
2. ./do reset-data       (drop + reupload to Aito; estimate below)
3. ./do precompute       (per-customer + landing + help_related)
4. verify perf at scale  (the table at the end)
5. deploy
```

### 1. Generate fixtures

```sh
uv run python data/generate_fixtures.py
```

Output:
- `data/invoices.json` (~480 MB at 1 M rows; current 128 k = 64 MB)
- `data/bank_transactions.json` (~150 MB)
- `data/overrides.json`, `data/customers.json`, etc. (small)

Time: ~5 min on a laptop. Memory: ~3 GB peak.

### 2. Reset Aito

```sh
./do reset-data
```

This drops every table and re-uploads from the new fixtures.

Estimated duration at 1 M:
- Current 128 k load takes ~10 min.
- Linear scaling → **~80 min** at 1 M, possibly more if Aito's
  index-build time is super-linear.

### 3. Precompute

```sh
./do precompute --workers 4
```

Time at medium scale was 38 min for top 10 customers (4 workers,
228 s/customer avg). At 1 M scale, the largest customer goes from
16 k → 128 k invoices (8×). Expected per-customer time on the top
tier: 30 min. With workers=4 and the geometric tail, full sweep
estimate: **6–8 hours wall-clock**.

Strategy: don't run the full 256 customers immediately. Start with
top 10–20 (the ones a sales walkthrough actually visits) and run
the long tail overnight or on a cron.

```sh
./do precompute --workers 4 --limit 20    # demo path: top 20 only
./do precompute --workers 4               # later: full sweep
```

### 4. Verify perf at scale

Hit each demo route, capture cold + warm latency, compare to the
endpoint perf table at the bottom of `aito-perf-findings.md`.

| route | what to check at 1 M |
|---|---|
| `/api/multitenancy/landing` | Should still be 10–30 ms (precomputed JSON, doesn't touch Aito tables). |
| `/api/multitenancy/shared_vendors` | Reads from `landing` — same, 10–30 ms. |
| `/api/customers` | Live `_search` against 256 rows, unaffected. ~290 ms. |
| `/api/help/search` | Live `_recommend` over `help_impressions`. Re-time cold path; the 12.8 s warmup ceiling may grow. |
| `/api/help/related` | Precomputed. Should stay 10–30 ms. |
| `/api/help/stats` | Two `_search limit:0` counts — Aito's count cost on 1 M-row tables is the watch item. |
| `/api/invoices/pending?customer_id=CUST-0000` | Precomputed. 50 invoices × 128 k history (vs 16 k). Watch the `prediction_log` writes during `predict_invoice` — they may be the slow part. |
| `/api/matching/pairs` | Precomputed. Watch precompute time, not serve time. |
| `/api/anomalies/scan` | Precomputed. Same. |
| `/api/quality/predictions` | Precomputed (`_evaluate` runs at precompute time). `_evaluate` is the slowest known operation; expect minutes per run on the largest customer. |
| `/api/formfill/predict` | **Live** — fan out 5–7 `_predict` calls in parallel. The only hot live path. Each `_predict` cold against 128 k-row history is the key flag. |
| `/api/formfill/templates` | Already cached, but watch `predict_template`'s `_search limit:50` cold time. |

### 5. Deploy

Standard pipeline: `docker build`, push, swap. The two cross-tenant
JSON files (`landing.json`, `help_related.json`) are checked in via
git so they ship with the image.

---

## What to flag during the run

For each operation that takes >100 ms warm or >2 s cold, log:

- The Aito query JSON (capture from `aito_call_log` ContextVar
  or `X-Aito-Ms` response header)
- Cold + warm latency at medium scale (already in
  `aito-perf-findings.md`)
- Cold + warm latency at 1 M scale (new column to add)
- Whether the slowdown is super-linear in row count

Update `aito-perf-findings.md` with a "1 M scale" column to the
endpoint perf snapshot table. Anything that grew super-linearly is
a core-team flag.

## Rollback

If the 1 M scale breaks something on prod:

1. Keep the medium-scale `data/precomputed/landing.json` and
   `data/precomputed/help_related.json` checked in. They serve as
   the bootstrap fallback when `precompute_entries` in Aito has
   the new (broken?) payload.
2. Revert by re-running `./do reset-data` against medium fixtures
   and `./do precompute` to overwrite the Aito-side store.
3. The image itself doesn't need rebuilding — bootstrap JSON is
   the only thing in git.
