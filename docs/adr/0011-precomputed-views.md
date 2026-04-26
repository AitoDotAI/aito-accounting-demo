# 0011. Precomputed views for hosted demo

**Date:** 2026-04-26
**Status:** accepted

## Context

The Predictive Ledger demo has nine views, eight of which are
read-only summaries (invoices pending, payment matching, mined
rules, anomaly scan, quality overview, prediction accuracy, rule
performance, override patterns). Each one calls Aito with a mix of
`_predict`, `_evaluate`, `_relate`, and `_search` queries. On a
cold customer that adds up to 10–20 seconds before the first paint.

For a public, hosted demo this is a problem on three axes:

1. **First-impression latency.** A CTO opens the URL, clicks an item
   in the nav, and waits 15 seconds. The "instant predictions" claim
   evaporates before the demo gets a chance.
2. **Aito quota.** The hosted demo has unknown traffic patterns;
   serving every page view through Aito risks a thundering herd
   blowing the quota.
3. **Cost predictability.** With live calls, the per-month Aito
   spend scales with traffic. With precomputed JSON, it's flat.

The eight summary views are deterministic — given the same fixture
data, the predictions don't change between requests. That's the
opening.

## Decision

Pre-compute the JSON for every read-only view at build/data-load
time and serve the static JSON. The only live Aito call from a
browser session is interactive Form Fill.

Concretely:

- **`data/precompute_predictions.py`** loops over all customers,
  writes one subdir per customer at
  `data/precomputed/{customer_id}/{name}.json` (seven files per
  customer: invoices_pending, matching_pairs, rules_candidates,
  anomalies_scan, quality_overview, prediction_accuracy,
  rule_performance).

- **Each precompute function delegates to the same service function
  the live endpoint uses** (`compute_prediction_quality`,
  `compute_rule_performance`, `match_all`, `scan_all`, etc.). This
  is the load-bearing decision: precomputed JSON is byte-identical
  to a warm cache hit, so the frontend cannot tell the difference.

- **Endpoints check the precomputed file first**, fall back to live
  Aito + L1/L2 cache when the file is absent. Dev keeps working
  against fresh fixtures without precomputing; the hosted image
  ships with precomputed data baked in.

- **`./do precompute`** runs the script. Flags: `--customers`
  (subset), `--limit` (first N), `--workers` (parallel customers),
  `--skip-existing` (resume).

- **Cache warmup at server startup is skipped** when
  `data/precomputed/` has any contents — the precomputed JSON is
  the warm layer.

## Aito usage

Precompute time uses the same operators the endpoints already use:
`_predict`, `_evaluate`, `_relate`, `_search`. No new query shapes.

At serve time, the only Aito call from a hosted-demo session is the
interactive `_predict` from `/api/formfill/predict`. Help search
and recommendations stay live too — they're interactive and the
ranking changes with the impressions feedback.

## Acceptance criteria

- `./do precompute` produces 7 JSON files under
  `data/precomputed/{customer_id}/` for every customer in
  `data/customers.json`.
- Every read endpoint serves a precomputed file when one exists,
  with `<20 ms` response time.
- Every read endpoint falls back to live Aito when the file is
  absent, with the same response shape as the precomputed file.
- Frontend renders all eight read-only views identically with or
  without precomputed data.
- Server startup is `<1 s` when precomputed data exists.

## Demo impact

- Hosted-demo cold start drops from 10–20 s to <100 ms per view.
- Aito quota usage in the hosted demo collapses to whatever Form
  Fill drives (a few `_predict` per session).
- The precompute step becomes part of the deploy pipeline:
  `./do generate-data` → `./do load-data` → `./do precompute` →
  `./do azure-deploy`.

## Out of scope

- **Live re-precomputation when fixtures change.** For now, the
  fixture data is generated once and the precompute is run once.
  When fixtures change you re-run both. A scheduled refresh cron
  could be added later if the fixture generator becomes
  non-deterministic.

- **Per-tenant fresh predictions.** Every read endpoint serves the
  same precomputed JSON to every visitor of a given customer. This
  is fine for a demo; a real product would want some
  request-scoped freshness.

- **Precomputing the `quality/evaluations` matrix.** Multi-target
  `_evaluate` cross-product is expensive (one call per target per
  domain) and the user-facing latency is acceptable behind a TTL
  cache. Revisit if the page becomes a hot path.
