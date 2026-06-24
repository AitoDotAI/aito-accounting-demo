# 0014. Pattern Rule Discovery — `$patterns` conjunction mining

**Date:** 2026-06-23
**Status:** accepted

## Context

ADR 0006 shipped Rule Mining with single-field `_relate`: for each
condition field (`vendor`, `category`, `vendor_country`) we run one
`_relate` per distinct value and surface the strongest single-feature
rule, e.g. `category="telecom" → GL 6200, 17/17`.

Two limitations followed directly from that design, both listed as
*out of scope* in ADR 0006:

1. **No multi-field rules.** Real accounting rules are often
   conjunctions — `vendor="Telia" AND category="telecom" → GL 6200`.
   The single-field miner cannot express these. The `sub_patterns`
   endpoint (`src/app.py`) fakes them by chaining `_relate` calls with
   a discovered condition baked into the `where` — a "poor-man's
   pattern proposition" that is N extra round-trips and only ever finds
   2-deep conjunctions anchored on an already-known rule.

2. **One `_relate` per distinct field value.** Mining cost scales with
   cardinality (every vendor, every category), and the heavy lifting —
   deciding *which* feature combinations matter — happens client-side
   by post-filtering single-feature results.

Aito now exposes `$patterns`, which mines AND-conjunctions
(`A & B & C → X`) server-side in a single `_relate`, with `$related` as
an explicit cost/relevance knob. This ADR adopts it and retires the
single-field miner and the `sub_patterns` chaining hack.

## Decision

### Aito usage

Mine conjunction rules per GL code with one `_relate` call. The
`where` pins the prediction target; `$patterns` discovers the
left-hand-side conjunctions; `$related` narrows the candidate feature
set to the top-`k` most related to the target before mining, bounding
both scope and latency.

```json
{
  "from": "invoices",
  "where": { "gl_code": "6200", "customer_id": "acme" },
  "relate": {
    "$patterns": {
      "$related": {
        "relate": ["vendor", "category", "vendor_country",
                   "cost_centre", "approver", "payment_method"],
        "k": 8,
        "to": { "gl_code": "6200" }
      }
    }
  },
  "select": ["related", "condition", "lift", "fs", "ps"],
  "orderBy": "lift",
  "limit": 8
}
```

Each hit's `related` is a ready-to-reuse `$and` proposition:

```json
{
  "related": { "$and": [
    { "vendor":   { "$has": "Dottoressa Oy" } },
    { "category": { "$has": "consulting" } }
  ] },
  "condition": { "gl_code": { "$has": "5400" } },
  "lift": 8.0,
  "fs": { "f": 836.36, "fOnCondition": 836.36, "fCondition": 2001, "n": 16000 }
}
```

**Discovery, then exact counts — the crux of this change.** `$patterns`
is used only to *discover* which conjunctions matter. Its `fs` are
**smoothed model estimates, not exact counts**: note `f = 836.36` is
*fractional*, and the learner rounds the rule to deterministic
(`fOnCondition = f`, i.e. 100%). The real data has exceptions — exact
`_search` says 831 invoices match this conjunction and 16 of them are
*not* GL 5400, so precision is 815/831 = **98.1%**, not 100%. Trusting
the estimate prints a "100%" headline that the exact-search drill-down
immediately contradicts (an invoice booked to a different GL), and breaks
the demo's "exact historical counts, not ML estimates" promise.

So after discovery, the service computes every displayed number with
exact `_search` counts (`limit: 0` → `total`), all scoped to the
customer:

| Quantity   | Exact `_search` count                                   |
| ---------- | ------------------------------------------------------- |
| precision  | `count(clauses & GL) / count(clauses)`                  |
| coverage   | `count(clauses & GL) / count(GL)`                       |
| lift       | `precision / (count(GL) / count(scope))`                |

These are the same exact matches the drill-down uses, so "815 of 831"
agrees with the invoices it lists. Discovery still asserts the response
`condition` is the GL target (not a feature) — otherwise the
conjunctions are mined against the wrong target (ADR's nested-`from`
note below).

`$related.by` defaults to `infoGain` (classification-style: anti-
correlations are informative too). We keep the default — accounting
rule discovery is classification, not basket affinity.

**Multi-tenancy — nested `from`, not a `where` filter.** Verified live
during implementation: putting `customer_id` in the `where` alongside
the GL target breaks `$patterns`. The linked `customer_id` becomes the
condition and the support counts come back over the *global* table
(`n=128000`), not the tenant (`n=16000`) — silently wrong per-customer
numbers. So `relate_patterns()` scopes the row population with a nested
`from` (`{"from": "invoices", "where": {"customer_id": …}}`) and keeps
`where` as the pure target. A side effect is that `$related` can still
surface candidate features that never co-occur with the target in this
tenant (estimated `fOnCondition = 0`); discovery drops them with the
positive-lift filter, and the exact `MIN_SUPPORT` gate catches the rest.

### Backend

- Rewrite `src/rulemining_service.py` as two stages.
  `discover_conjunctions()` parses a `$patterns` response into candidate
  `$and` conjunctions (keeping positive ones, de-duplicating, asserting
  the `condition` is the GL target). `build_candidate()` then turns
  **exact `_search` counts** into each `RuleCandidate`. A candidate's
  `pattern_display` renders the conjunction (`vendor="Telia" AND
  category="telecom"`); single-clause conjunctions render naturally.
- Exact precision drives `classify_strength` (unchanged thresholds:
  Strong ≥95%, Review ≥75%, Weak <75%). `MIN_SUPPORT` gates on the exact
  `rule_match` count (rows where the rule fires *and* lands on the GL).
- **Positive patterns only.** We list rules whose conjunction makes the
  target GL *more* likely than its base rate (`lift > 1`, computed
  exactly) and drop the rest. `infoGain` mining re-surfaces every strong
  rule as a near-zero anti-pattern (`lift ≈ 0`) for each *other* GL —
  informative for classification, but noise in a rule-discovery list.
- Cost: `$patterns` discovers, then a handful of `limit:0` `_search`
  counts per GL price the rules exactly (~2 per rule + 1 per GL + 1 for
  scope). Counts are cheap (~tens of ms) next to the heavy mining call.
- Retire the `/api/rules/sub_patterns` chaining endpoint. Conjunctions
  it used to approximate are now first-class in `/api/rules/candidates`.
  `/api/rules/drilldown` takes the rule's `clauses` and `_search`es them
  to list the matching invoices — the same exact match the counts use.

### Performance

Pattern mining is heavier per call (~9-11 s server-side on the shared
instance at 128 k rows) than a single-field `_relate`. Two mitigations,
both already part of the project's machinery:

- `$related` with a small `k` (default 8) caps the mining focus. In
  testing, narrowing six candidate fields trimmed a representative call
  from 10.9 s to 9.0 s; the win grows with candidate-field count.
- Mining stays on the **precompute / warm-cache** path (it already is
  for `rules:{customer_id}`), never synchronous in a user request.
  `GET /api/rules/candidates` serves precomputed → cache → live, in
  that order, exactly as today.

## Acceptance criteria

- A user opens Rule Mining and sees multi-field rules, e.g.
  `vendor="…" AND category="telecom" → GL 6200`, with support ratio,
  coverage %, lift, and a Strong/Review/Weak badge.
- Support ratio is the exact rule precision (`count(clauses & GL) /
  count(clauses)`) and equals the match/disagree split the drill-down
  shows; coverage is the exact share of the GL the rule explains.
- Single-feature rules still appear and read naturally (no dangling
  "AND").
- Candidates are sorted strongest-first and the metrics row
  (count / strong / coverage gain) still populates.
- When Aito is unreachable the static mockup remains visible.
- Tests verify: `$and` conjunction parsing, the precision/coverage
  role inversion, single- vs multi-clause rendering, strength
  classification, and `MIN_SUPPORT` gating.
- `./do aito-check` gains a `$patterns` sanity assertion (response has
  `hits`, each `related` is an `$and`/field proposition, `lift` finite,
  `fs.fOnCondition ≤ fs.f`).

## Demo impact

The Rule Mining walkthrough in `docs/demo-script.md` upgrades from
"Aito finds single-feature rules" to "Aito discovers the multi-field
rules a human would write" — a stronger differentiator. Support ratios
stay real (`fs`-derived), now over conjunctions.

## Out of scope

- Promote/dismiss persistence (unchanged from 0006).
- `$related.by: lift` / basket-affinity mining — not the accounting use
  case.
- Tuning `k`/`limit` per customer; defaults only.

## Amendment — inputs-only, multi-target, `amount_band`

A review caught a **leakage** flaw in the first cut: the candidate fields
included `approver` and `cost_centre`, which are *outputs* assigned during
coding/approval, not known when an invoice arrives. A rule like
`vendor="X" AND approver="Y" → gl_code=Z` can't fire as a routing rule —
the approver is decided by the very workflow we're automating. In the
fixtures the leak is structural: `vendor → category → gl_code`, and
`approver` is a *sibling* output of `category` (assigned by category, with
an amount escalation). So `approver` was a proxy for `category` that made
rules look richer than they were.

Three corrections:

1. **Inputs only.** Candidate clauses are restricted to fields known at
   intake: `vendor, category, vendor_country, amount_band`. Outputs are
   never inputs.

2. **`amount_band`.** `$patterns` can't mine a `Decimal` into threshold
   clauses (verified: it ignores raw `amount`), so the data carries a
   categorical band derived from amount at intake (small <€1k / medium /
   large ≥€10k). This is what lets amount-conditional rules exist.

3. **Multiple targets.** We mine rules *for* each output an AP clerk codes
   — `gl_code` and `approver` — each predicted from the inputs above.
   This is where the genuine multi-field rules live:
   - `gl_code`: mostly single-input (`category=insurance → 5300`), plus a
     **capitalization** rule — large IT/software/maintenance purchases
     book to a capital account: `category=it_equipment AND
     amount_band=large → 1600`.
   - `approver`: genuinely multi-input — a category's normal approver, but
     `amount_band=large` escalates to a senior signer, so the same
     category routes to different approvers by amount band.

The fixture generator gained the `amount_band` field and the
capitalization split (the only place `gl_code` depends on more than
vendor/category); the escalation that drives the `approver` rules already
existed. `CANDIDATE_FIELDS` and `TARGET_FIELDS` in `rulemining_service.py`
encode the input/output split; `/api/rules/drilldown` takes a
`target_field` so it audits approver rules the same way it audits GL
rules.
