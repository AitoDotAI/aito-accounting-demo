# Report: the `$on` conditional relate on Aito v2 (collections)

**Date:** 2026-07-13 · **Context:** v2 migration of the accounting demo
(`docs/adr/0017-aito-v2-migration.md`) · **Audience:** Aito core / query team

## Summary

The rule-diagnostics feature (ADR 0015) explains *why a mined rule has
exceptions* by relating a rule's remaining input features to its output,
**within the rule's matched population**, using a conditional relate:

```jsonc
{ "from": "invoices",
  "where":  { "$on": [ {gl_code:"1600"}, {vendor:"K. Itäluoma Oy", category:"maintenance"} ] },
  "relate": ["amount_band", "vendor_country"] }
```

On **v1** this returns, per feature value, `fs.f` / `fs.fOnCondition` (exact
agree/total) and a `lift = agreement_ratio / base_rate`. That's all the
diagnostic needs.

On **v2 collections** the same query runs, but is unusable for the diagnostic
for three independent reasons:

1. **`fs`/counts are omitted** from the response.
2. **`lift` is wrong** — it doesn't match `agreement_ratio / base_rate`.
3. **`$on` structurally hides the exception values** — the ones the diagnostic
   exists to find.

We shipped a client-side workaround (recompute everything from exact
`_query limit:0` counts), but each is a core-side gap worth fixing so `$on`
is usable directly.

All figures below are live from `env.v2-demo` (branched from master),
customer `CUST-0000`.

---

## Reference: what v1 returns (and the diagnostic needs)

For the population `vendor="K. Itäluoma Oy" AND category="maintenance"` and
target `gl_code=1600`, relating `amount_band`:

| amount_band | v1 `fs.f` | v1 `fs.fOnCondition` | agree ratio | v1 `lift` |
|---|---|---|---|---|
| large  | 327 | 322 | 322/327 = 0.985 | **1.08** |
| medium |  26 |   0 |   0/26  = 0.000 | **0.02** |

The diagnostic reads this as: *large drives agreement, medium is the whole
exception → suggest adding `amount_band="large"`.* `lift ≈ agree_ratio /
base_rate` (base_rate = 322/353 = 0.912; 0.985/0.912 = 1.08 ✓).

---

## Issue 1 — `$on` relate omits `fs` / counts

**Repro:** the query above with `select: ["related", "lift", "fs"]`.
**v2 response (per hit):** `{ "related": "{ amount_band:large }", "lift": … }`
— no `fs`, `f`, or `fOnCondition`, even though `fs` was explicitly selected.

**Impact:** no exact agree/total, so the diagnostic can't show "322/327" or
compute an agreement ratio. (v1 returns `fs` here.)

## Issue 2 — `$on` relate `lift` does not match `agreement_ratio / base_rate`

**Repro:** population `vendor="Dottoressa Oy" AND category="consulting"`,
target `gl_code=5400`, relate `amount_band`.

Ground truth (exact counts): base_rate = 815/831 = 0.981.

| amount_band | agree/total | true ratio | expected lift (ratio/base) | **v2 `lift`** |
|---|---|---|---|---|
| medium | 764/778 | 0.982 | 1.00 | **1.62** |
| large  |  51/53  | 0.962 | 0.98 | **0.29** |

v2 reports `large` at **0.29** — implying strong *anti*-correlation — when its
agreement (0.96) is essentially the base rate. A lift-thresholded diagnostic
(agreement ≥ 1.05, exception ≤ 0.9) would **wrongly flag `large` as an exception
driver** and suggest refining the rule to `medium`, which is incorrect. v1's
lift here is ≈ 0.98 (correctly "no signal").

## Issue 3 — `$on` structurally hides the exception values (most damaging)

`$on: [target, population]` conditions the relate on **target = yes**. So a
feature value that **never co-occurs with the target** — i.e. a pure exception —
has zero rows in the conditioned set and **is not returned at all**.

**Repro:** the K. Itäluoma population above. `amount_band="medium"` is `0/26`
(never `1600`). Relating over the `$on`-conditioned set returns **only
`large`** — `medium`, the entire exception and the reason to run the diagnostic,
is invisible.

**Impact:** even if Issues 1–2 were fixed, enumerating candidate values *through*
`$on` cannot surface the exceptions. The diagnostic's whole purpose is to find
the values that mark disagreement; `$on` hides exactly those.

---

## Impact on the migration & our workaround

ADR 0015 diagnostics cannot be built on v2 `$on` as-is. We made it work by
**not trusting the `$on` response**: enumerate each feature's values over the
**unconditioned** population, then compute `f`, `fOnCondition`, and
`lift = agree_ratio / base_rate` with exact `_query limit:0` counts
(`AitoV2Client.relate_features`). This reproduces v1's diagnostic output
exactly (same exception `medium 0/26`, same suggestion) — but at O(values)
extra round-trips per rule instead of one relate call.

## Recommendations (core side)

1. **Return `fs` from `$on` relate** (`f`, `fOnCondition`, and `fCondition`),
   matching v1 — so callers get exact agree/total in one call.
2. **Fix `$on` relate `lift`** to equal `P(value | target, population) /
   P(value | population)` (equivalently the v1 `agree_ratio / base_rate`
   semantics). The current values (e.g. 0.29 for a 0.96-agreement value) are
   misleading.
3. **Enumerate over the unconditioned population.** For a "why the exceptions"
   diagnostic, the relate must report values that *don't* co-occur with the
   target (agree = 0). Either don't drop zero-on-condition values, or offer a
   relate mode that ranks a population's feature values by their agreement with
   a target (including the disagreeing ones).

Items 1–2 make `$on` correct; item 3 makes it *sufficient* for exception
diagnostics. With all three, the demo could drop the count-recompute workaround
and use a single relate call as on v1.
