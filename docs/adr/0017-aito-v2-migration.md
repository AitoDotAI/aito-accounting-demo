# 0017. Migrate to the Aito v2 API (unified query + collections + envs)

**Date:** 2026-07-12
**Status:** accepted

> **Update 2026-07-14.** The predictive scope is implemented and running on
> `v2-demo` behind `AITO_V2_ENV`: smart form-fill, invoice processing
> (predict + `$why` + rule matching), vendor templates, and rule mining
> (discovery + drilldown + diagnostics). `AitoV2Client` is a drop-in for the v1
> client's `predict` / `relate` / `relate_patterns` / `relate_features` /
> `search` interface, so the services are passed it unchanged. The core update
> (rev `b97566fd`) resolved the predict segment-sensitivity and `$on` issues that
> had blocked this; see `docs/notes/aito-v2-core-issues.md`.
>
> **Update 2026-08-15.** The three deferred verbs were re-examined on rev
> `7d5c48a9`. This ADR's "Out of scope" claim below — *"their v2 forms aren't
> yet confirmed (no `_query` key exists for them)"* — was **half right**:
> `_match` and `_evaluate` really are not Query2 keys, but both survive as their
> own v2 endpoints, and `recommend` is a Query2 key. Result:
>
> - **`_evaluate` migrated.** The quality dashboard, the per-task evaluations
>   matrix, and the per-case diff table now run on v2 via
>   `AitoV2Client.evaluate()`, which unwraps v2's `{"kind","data"}` envelope and
>   aliases `cases[].top.$value` → `feature`. v2's metrics are a superset.
> - **`_match` (payment matching) stays on v1** — v2's `_match` returns raw `$f`
>   counts, never `$p`/`$why`, and cannot rank an unseen payment (every candidate
>   ties at 0). Core issue **V2-12**.
> - **Help `recommend` stays on v1** — v2's `recommend` silently drops
>   disjunctive filters on linked fields, so the tenant-eligibility clause is
>   ignored and other customers' internal articles leak into results. Core issue
>   **V2-13**. No workaround; not papered over.
>
> The env was also renamed `env.v2-demo` → `v2-demo` by the core (the `env.`
> prefix is now reserved) — core issue **V2-11**.
>
> **Update 2026-08-31.** Re-verified against the first *current* deploy (rev
> `38a234a6`). **Both blockers above are fixed**, so neither "stays on v1"
> claim holds any longer:
>
> - **`_match`** returns a graded `$p`, generalizes to unseen evidence, and
>   honours `select` / `$why`. (Payment matching had already migrated anyway —
>   it uses `_predict` on the linked `bank_transactions.invoice_id`, not
>   `_match`.)
> - **Help `recommend`** honours `$or` / `$in` on linked fields; the drawer's
>   own query returns correctly-scoped results on v2. The help endpoints are
>   still wired to v1 in the code — that is now ordinary work, not a blocker.
>
> Also fixed: the `_evaluate` baseline now respects the tenant scope, and
> `meanRank` agrees with v1, so the quality metrics are v1-comparable again.
> Old `env.`-prefixed URLs resolve again (**V2-11**). Full round-3 evidence:
> `docs/notes/aito-v2-core-issues.md`.

## Context

Aito shipped a v2 API (`/api/v2`, beta). It is not a versioned reskin of v1 —
it changes three things that matter to this demo:

1. **One unified query endpoint.** `POST /api/v2/_query` absorbs most of the v1
   verb endpoints (`_predict`, `_relate`, `_recommend`, `_search`). The query
   type is now a top-level key inside one request body ("Query2"). The grammar,
   as enumerated by the server's own parse error (rev `7d5c48a9`): `from, let,
   where, search, get, predict, recommend, goal, relate, basedOn, orderBy,
   select, offset, exclusiveness, limit, config, fromWhere, fromLimit,
   relatePatterns, fromJoin, fromUnion`.

   The absorption is **not total**: `_match` and `_evaluate` have no Query2 key
   and remain their own endpoints (`POST /api/v2/_match`, `.../_evaluate`).
   "Not a `_query` key" therefore does not imply "no v2 form" — a distinction
   worth checking per verb rather than assuming either way.

2. **A new table kind: "collections".** v2 distinguishes *collections* (the
   native v2 type, full feature set) from *legacy tables* (anything uploaded via
   v1). On a legacy table, v2 serves basic query + `predict`, but `relate`/
   `$patterns` returns **HTTP 501 "supported on collections only"**. This demo's
   rule-mining + diagnostics (ADR 0014/0015) is built on `$patterns`, so the
   data must be rebuilt as collections to reach parity.

3. **First-class environments.** `POST /api/v2/_envs` branches an isolated
   environment off master; `promote` merges it back. This is how we get a
   "separate aito-env" for v2 work without a second database or risk to the live
   v1 demo.

We want a v2 build of the demo running in its own environment, developed
alongside the working v1 demo, with every product/doc rough edge captured for
the Aito core team (`docs/notes/aito-v2-migration-feedback.md`).

## Decision

Stand up the demo on v2 **in a branched environment**, `v2-demo`, keeping
`env.master` (the live v1 demo) untouched.

- **Environment.** Branch `v2-demo` off master via `_envs`. Address it in
  the URL path: `…/db/aito-accounting-demo/env/v2-demo/api/v2/…`. The
  existing master API key authorizes env access — env auth is database-scoped,
  there is no separate env key.
- **Data as collections.** Rebuild the dataset as v2 collections in the env. The
  schema is a near-mechanical translation of `data_loader.SCHEMAS`
  (`type:"table"` → `type:"collection"`; columns, `link`, and `nullable` carry
  over — links verified functional in v2 collections).
- **Client.** Parameterize the client's hardcoded `/api/v1` base into a v2 base
  (with the `env/<name>` segment) and route queries through `_query`. Keep the
  v1 client path intact so the v1 demo and `./do` commands keep working; select
  by config, not by deleting the v1 path.
- **Response adaptation.** Handle the v2 response-shape changes at the service
  boundary (see Aito usage). Do not leak v2 shapes into the frontend beyond what
  the existing view models already expect.
- **Rule mining stays live throughout.** v1 `_relate $patterns` still mines the
  legacy tables today, so the running demo's rule-mining keeps working while the
  v2 collection path is built in parallel.

Rollout is incremental: (1) config + v2 client plumbing, (2) collection loader +
env build, (3) port read/predict paths and adapt `$why`, (4) port rule-mining to
collections, (5) verification + demo-script/README updates. Each is its own
reviewable step on this branch.

## Aito usage

All queries go to `POST …/env/v2-demo/api/v2/_query`. Confirmed live shapes:

**Predict** (value moved from v1 `feature` to `$value`):
```jsonc
// request
{ "from": "invoices", "where": {"vendor": "Kesko Oyj"},
  "predict": "gl_code", "select": ["$p", "$value", "$why"], "limit": 3 }
// hit
{ "$p": 0.172, "$value": "4400", "$why": { "type": "product", "factors": [ … ] } }
```
`$why` is live but reshaped into a nested factor tree
(`baseP` / `product` / `normalizer` / `calibration`) rather than v1's flat
proposition list — the explanation UI adapts to the tree.

**Rule mining** — `$patterns` on a **collection** (same request shape as v1):
```jsonc
{ "from": "invoices", "where": {"gl_code": "1600"},
  "relate": {"$patterns": {"$related": {"relate": ["vendor","category","amount_band"],
                                        "k": 6, "to": {"gl_code": "1600"}}}},
  "orderBy": "lift", "limit": 8 }
```
Each hit's `related`/`condition` come back as structured propositions
(`{"$and": [{"vendor": "Bronex"}, …]}`) that `parse_conjunction` reads directly.
(They were stringified pseudo-syntax when this ADR was written; core rev
`b97566fd` fixed that and the client-side parser was deleted.) The two-stage
design — discover conjunctions, then recompute exact support with a `limit:0`
count query — is unchanged from v1.

**Evaluation** — `_evaluate` keeps the v1 request body but reshapes the reply:
```jsonc
// request (unchanged from v1)
{ "testSource": {"from": "invoices", "where": {…}, "limit": 50},
  "evaluate": {"from": "invoices", "where": {"vendor": {"$get": "vendor"}, …},
               "predict": "gl_code"} }
// response: metrics nested under `data`, and cases use `$value`, not `feature`
{ "kind": "evaluation",
  "data": { "accuracy": 0.57, "baseAccuracy": 0.17, "logLoss": 1.08, "ece": 0.20,
            "cases": [{"accurate": true, "top": {"$value": "4400", "$p": 0.98}}] } }
```

**Schema / data** (env-scoped, master key):
- Create collection: `PUT …/api/v2/schema/{name}` `{"type":"collection","columns":{…}}`.
- Load: `POST …/api/v2/data/{name}/batch` with a JSON array of rows.

See `docs/notes/aito-v2-migration-feedback.md` for the full probe log, and
`docs/notes/aito-v2-core-issues.md` for the core issues. The two that kept a
feature on v1 — **V2-12** (`_match` cannot rank) and **V2-13** (`recommend`
drops linked-field disjunctions) — were both fixed in core on 2026-08-31; see
round 3 in that file.

## Acceptance criteria

- Given the master key, a developer can run `./do` (new subcommand) to branch
  `v2-demo` and build the full dataset as collections, idempotently.
- When the app is configured for v2, invoice GL/processor prediction returns the
  same top-1 answers as v1 for the demo's canonical invoices (value read from
  `$value`), with a `$why` explanation rendered from the v2 factor tree.
- When rule mining runs against the v2 collections, it discovers the same
  headline rules as v1 (capitalization → 1600, escalation → senior approver),
  with support ratios matching the drill-down (exact-count stage preserved).
- The v1 demo (`env.master`, `./do demo`) is byte-for-byte unaffected — no v2
  code path executes unless v2 config is set.

## Demo impact

No change to the *user-facing* demo path yet. `docs/demo-script.md` gains an
appendix describing how to run the demo against v2 (`v2-demo`) once parity
is reached. If v2 becomes the default, the main script is revisited then — out
of scope for this ADR.

## Out of scope

- Promoting `v2-demo` into master / making v2 the default demo. This ADR
  builds and proves the v2 path; the cutover is a later decision.
- Migrating `_similarity` and `_aggregate` — still unmapped, and not on the
  demo path. (`_evaluate` was migrated 2026-08-15; `_match` and help
  `recommend` were attempted and were blocked on core issues V2-12 / V2-13,
  both since fixed — see the 2026-08-31 update at the top.)
- Any change to fixture *generation* (`generate_fixtures.py`). v2 consumes the
  same fixtures; only the upload target/format changes.
- Performance tuning (optimize/backfill semantics on collections at 128k+ rows)
  beyond confirming correctness. Scale hardening is a follow-up.
