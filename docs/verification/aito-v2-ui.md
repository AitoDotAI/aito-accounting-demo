# v2 UI verification — `AITO_V2_ENV=v2-demo`

**Date:** 2026-08-29 (D5 added 2026-08-30) · **Core rev:** `3de8f4f7` (built 2026-08-27)

> All findings here were measured against the **deployed** `shared.aito.ai`,
> which was on `3de8f4f7` throughout. That build is not current — core fixes
> landing in main are not visible from here, so nothing below should be read as
> "core has not fixed this", only as "the deployed build behaves this way".
>
> **Superseded in part, 2026-08-31 (rev `38a234a6`).** The deploy is now
> current and every core issue this pass depended on has been re-verified —
> see `docs/notes/aito-v2-core-issues.md`, round 3. Two items below have
> changed: **D5 is resolved** and **Help is no longer blocked**. The
> corrections are inline.
**Branch:** `feat/0017-aito-v2-migration` · **Method:** app served from
`frontend/out`, driven in Chrome; every view loaded and its rendered text
captured. v1 comparison run on the same build with `AITO_V2_ENV` unset.

## Verdict

Every migrated view renders correctly on v2. Two real defects were found and
fixed during the pass; one blocker and one performance gap remain.

| View | v2 | Notes |
|---|---|---|
| Invoice Processing | ✅ | 85% touchless, 0.93 avg conf, 20 pending, 19 Aito / 1 rule |
| Smart Form Fill | ✅ | 27 vendors, 6 quick-start templates from v2 |
| Rule Mining | ✅ | 41 candidates, 34 strong, +77.2% coverage, exact supports + lifts |
| Payment Matching | ⚠️ | 8 matched / 12 unmatched — identical to v1; explanation weak (see D3) |
| Anomaly Detection | ✅ | 1 anomaly over 15 scanned, with reason + recommended action |
| Quality · System Overview | ✅ | 82% automation, 19% rules, 63% Aito, 9% human — identical to v1 |
| Quality · Prediction Quality | ✅ | **97% accuracy**, 50-case table. Baseline/gain/meanRank render but are not v1-comparable — see D5 |
| Quality · Evaluations Matrix | ✅ | GL 98%, approver 94%, bank-txn 100%, help-click 73% |
| Multi-tenancy landing | ✅ | Renders; shared-vendor cards populated |
| Help | — | Still v1 in this pass — core **V2-13** has since been fixed, so it can migrate |

## Defects found and fixed in this pass

**D1 — `$why` silently degraded to the base rate (fixed).**
The explanation popup — the demo's headline differentiator — rendered only
"BASE PROBABILITY" on v2, with every per-feature factor missing. No error.

Root cause was *not* the API: v2 returns a `$why` tree structurally identical
to v1's, with the same `relatedPropositionLift` factors (v2 actually returns
one more). The parser was the problem. `_collect_props` understood only v1's
encoding — values wrapped in an operator (`{vendor: {$has: "Kesko"}}`) and
conjunctions grouped under `$and`. v2 returns the bare value
(`{vendor: "Kesko"}`) and groups under `$group`, so every proposition was
skipped and each factor discarded as empty.

`_collect_props` now accepts both encodings. Verified live on an Aito-routed
invoice: base + patterns at lift 8.35 (vendor + category + amount as one
`$group` card), 4.71 and 1.82 (description tokens), with `<mark>` highlights.

**D2 — latency badge went dark on v2 (fixed).**
`AitoV2Client` never fed the `aito_call_log` contextvar, so `X-Aito-Ms` /
`X-Aito-Calls` were absent and the topbar badge — the demo's standing answer to
"is the predictive layer fast?" — showed nothing. Additionally
`_LATENCY_REPORTED_PREFIXES` predated v2 and lacked `/_query`, which would have
zeroed the badge even once recording worked. Both fixed; the badge now reads
e.g. `_query 247ms`.

## Open items

**D3 — Payment Matching explanation is uninformative on v2.**
Matching itself is correct and matches v1 exactly (8 matched / 12 unmatched,
near-identical confidences). But the "Why this match?" panel reads
`BASE PROBABILITY … 0% … 0% = 50%`. Cause: predicting a 128k-cardinality
`invoice_id` yields `$p ≈ 1.9e-05`, which rounds to 0% in the UI, so the panel
implies Aito contributed nothing when in fact it ranked the right invoice first.
The *status* thresholds (0.30 / 0.15) need no change — `aito_p` is only half the
blend and `amt_score` carries it. What needs revisiting is how the panel
presents a legitimately tiny probability. Not a blocker; it is a presentation
bug in one panel.

**D4 — cold-path latency is the real gap for a v2 demo.**
On v1 the heavy views are served instantly from the precompute bootstrap. v2
deliberately bypasses precompute (it is v1-derived), so every view computes
live on first hit:

| Endpoint | v2 cold |
|---|---|
| `quality/overview` | 16–53 s |
| `formfill/templates` | 21 s |
| `anomalies/scan` | 37–56 s |
| `quality/evaluations` | 111 s |
| `rules/candidates` | 112 s |
| `quality/predictions` | 123 s |
| `matching/pairs` | **254–276 s** |

Warm, all are instant (single-digit ms). But a cold view shows `--` placeholders
long enough to read as broken — that is exactly what happened on the first
Quality pass in this session, which I initially misdiagnosed as a v2 rendering
bug before the v1 comparison showed it was purely cold-start.

**Before v2 can front a live demo, it needs a precompute pass of its own**
(`./do precompute` against the v2 env, written to a v2-keyed store), or the
cutover should be paired with warming. This is the largest remaining item and
is demo-side work, not a core issue.

**D5 — `_evaluate`'s baseline and rank are not comparable to v1.**
Accuracy itself is sound and comparable (v1 0.96 vs v2 0.98 on an identical
50-row evaluation). Three sibling metrics are not:

| metric | v1 | v2 |
|---|---|---|
| accuracy | 0.96 | 0.98 |
| baseAccuracy | 0.44 | 0.1723 |
| accuracyGain | 0.52 | 0.8077 |
| meanRank | 0.16 | 1.02 |

`baseAccuracy` diverges because v2 computes the majority-class baseline over the
**entire collection**, ignoring the `customer_id` scope in the evaluate `where`.
Counted directly: CUST-0000's majority GL is 4400 at 7 486/16 000 = 0.468, which
is what v1 tracks; the global majority is 22 063/128 000 = 0.1724, which is
exactly v2's number. So on v2 the displayed *gain* is inflated — +80.8pp where
the honest figure is +52pp — and the error grows with tenant count. `meanRank`
is 0-based on v1 and 1-based on v2, so v2's 1.13 and v1's 0.16 are equivalent
despite the UI labelling the column "lower = better".

The Quality views surface `baseAccuracy`, `accuracyGain` and `meanRank`
directly, so **on v2 those three cells should not be read as v1-comparable**
until the core issue is resolved. Filed on `td-20260816070052009786` with the
full root cause. Accuracy, geomMeanP and the per-case table are unaffected.

> **D5 is resolved as of rev `38a234a6` (re-measured 2026-08-31).**
> `baseAccuracy` now respects the `customer_id` scope — the same 50-row
> evaluation gives v1 `0.44` / v2 `0.4680` (was `0.1723`), so the inflated
> `+80.8pp` gain is gone. `meanRank` reads `0.1` on **both**. One harmless
> convention difference is left: v1 takes the base rate over the 50-row test
> sample (22/50), v2 over the training population (7464/15950). Both are
> honest, so the three cells are comparable again — read the small
> `baseAccuracy` delta as a sampling difference, not an error.

**Blocked — Help.** Still on v1. Core **V2-13**: v2's `recommend` silently drops
disjunctive filters on linked fields, so the tenant-eligibility clause is
ignored and other tenants' internal articles are returned with a 200.
Re-verified still broken on rev `3de8f4f7`. Not worked around.

> **Unblocked as of rev `38a234a6` (2026-08-31).** `$or` and `$in` on a linked
> field now filter correctly. `help_service.py`'s ranking query, sent
> unchanged, returns 25 correctly-scoped candidates (20 global + CUST-0000's
> own 5) with the linked-field `select` resolving as before. The drawer is
> still wired to v1 in the code — migrating it is now ordinary work, not a
> blocked item.

## Not verified

- Interactive override / bulk-override write paths.
- `formfill/submit` end-to-end (writes `prediction_log`).
- Customer switching across all 255 tenants (spot-checked CUST-0000, CUST-0007).
- Cross-browser / mobile layout.

## Reproduce

```bash
./do v2-build                       # build the v2 env (idempotent)
AITO_V2_ENV=v2-demo ./do dev        # serve the demo against v2
```
Unset `AITO_V2_ENV` for the v1 path, which this pass confirmed is unaffected.
