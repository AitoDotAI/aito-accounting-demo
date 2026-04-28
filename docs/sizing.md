# On-prem sizing guide

Aito ships as a fixed-licence, on-prem product. The right hardware
depends on dataset size and concurrency. This is a quick worksheet
based on the demo's measured behaviour, extrapolated to common SaaS
scales.

## What we measured

The Predictive Ledger demo runs against an Aito instance with:

| Layer | Records |
|-------|---------|
| `customers` | 255 |
| `invoices` | 128 000 (24-month spread) |
| `bank_transactions` | ~68 000 |
| `corporate_entities` | 1 362 vendors |
| `overrides` | ~7 500 |
| `help_articles` + `help_impressions` | 120 + 14 580 |

Operator latency (warm `httpx` connection, idle Aito, server work
only — i.e. wall-clock minus the ~63 ms RTT to `shared.aito.ai`):

| Operator | Server work | Notes |
|----------|------------|-------|
| `_search` 20 hits, `where: customer_id` | **~22 ms** | flat across 16K-, 4K-, 250-invoice customers |
| `_search` 100 hits | ~75 ms | scales with response size |
| `_search` 1000 hits | ~440 ms | dominated by serialization |
| `_predict gl_code` | **~57 ms** | one target field, conditional probability |
| `_predict approver` | ~67 ms | similar |
| `_relate` 5 hits | ~17 ms | rule discovery |
| `_evaluate` 50 samples | **~7 990 ms** | leave-one-out cross-validation per case |
| `_recommend` (impressions) | ~100–200 ms | goal-oriented ranking |

The headline: indexed reads are **millisecond-class**.
`_evaluate` is the only operator that takes seconds, because it's
running cross-validation per test case at query time — not a
batch read.

## Scaling rules of thumb

Aito's index is a probabilistic graph over field values. Memory
and disk both grow roughly linearly with the number of (row × indexed
field) cells. Latency for `_search` and `_predict` is logarithmic
in row count for indexed-field where clauses, so doubling the row
count adds milliseconds, not seconds.

In practice, on commodity hardware (8-core, NVMe disk):

| Dataset | Index in RAM | Disk on NVMe | `_search` 20 hits | `_predict gl_code` | `_evaluate` 50 samples |
|---------|--------------|--------------|-------------------|--------------------|------------------------|
| **128 K invoices** (this demo) | ~150 MB | ~400 MB | ~22 ms | ~57 ms | ~8 s |
| **1 M invoices** | ~1 GB | ~3 GB | ~30 ms | ~70 ms | ~10 s |
| **10 M invoices** | ~8 GB | ~25 GB | ~50 ms | ~110 ms | ~15 s |
| **100 M invoices** | ~60 GB | ~200 GB | ~100 ms | ~200 ms | ~30 s |

These are extrapolations, not measurements. The shape (log-time on
indexed `where`, linear memory) is what to plan against; the
exact constants depend on field cardinality and how many fields
the index covers.

## Concurrency

Aito serves queries from the in-memory index, so concurrency is
bounded by CPU cores and JVM heap. Rule of thumb:

- **`_search`/`_predict`** — count one CPU thread per concurrent
  request. 8-core box → ~8 simultaneous `_predict` at full speed.
- **`_relate`/`_evaluate`** — heavier; budget 2 cores per concurrent
  request.

For a SaaS deployment with hundreds of concurrent end users, the
right pattern is what this demo does:

1. **Precompute every read-only view** at deploy time and serve
   the JSON from disk (`docs/adr/0011-precomputed-views.md`).
2. Route only the **interactive** Form Fill / Help Drawer /
   ad-hoc evaluator traffic to live Aito.

That collapses Aito-side concurrency to a small fraction of total
request volume.

## Memory + disk recommendations

| Workload | Cores | RAM | NVMe |
|----------|-------|-----|------|
| Single-tenant ≤ 100 K rows (dev/staging) | 4 | 8 GB | 50 GB |
| Demo / SaaS ≤ 1 M rows | 8 | 16 GB | 100 GB |
| Production ≤ 10 M rows | 16 | 64 GB | 500 GB |
| Production ≤ 100 M rows | 32 | 128 GB | 1 TB |

All numbers include 2× headroom for the JVM, OS, and parallel
operators. Disk is mostly the index; raw data on disk is roughly
the source CSV size.

## Hot-path vs cold-path

Aito's index optimises periodically. Right after a bulk insert,
queries against the new rows hit a smaller, less-optimised
sub-index until the next merge. For demo and SaaS workloads
where data churn is bounded:

- **Bulk-insert** at deploy time, then run `optimize_table` per
  table (the demo's `data_loader.py` does this automatically
  after every `./do load-data`).
- **Streaming inserts** for live-trained recommenders should run
  with `optimize` on a cron (hourly is usually enough).

The latency numbers above assume a freshly-optimised index.

## What changes at scale

- **Index optimisation time** scales linearly. 128 K rows
  optimise in ~2 s; 100 M rows take ~30 min.
- **Bulk insert throughput** is roughly 5 000 rows/s on commodity
  hardware. 100 M rows is a long afternoon, not a multi-day job.
- **`_evaluate`** stays slow because it's compute-bound. If you
  need to evaluate over 1 000 samples instead of 50, expect
  proportionally longer runs.

If you're sizing a hardware purchase, the load-bearing question is
**peak concurrent `_predict` calls/s on the live path**, not raw
row count. Most production deployments are bottlenecked by JVM
heap (memory) before they're bottlenecked by latency.
