# 0017. Migrate to the Aito v2 API (unified query + collections + envs)

**Date:** 2026-07-12
**Status:** proposed

## Context

Aito shipped a v2 API (`/api/v2`, beta). It is not a versioned reskin of v1 —
it changes three things that matter to this demo:

1. **One unified query endpoint.** `POST /api/v2/_query` replaces the v1 verb
   endpoints (`_predict`, `_relate`, `_recommend`, `_search`, `_match`, …). The
   query type is now a top-level key inside one request body ("Query2"). The
   confirmed grammar is: `from, let, where, search, get, predict, recommend,
   goal, relate, basedOn, orderBy, select, offset, exclusiveness, limit, config`.

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

Stand up the demo on v2 **in a branched environment**, `env.v2-demo`, keeping
`env.master` (the live v1 demo) untouched.

- **Environment.** Branch `env.v2-demo` off master via `_envs`. Address it in
  the URL path: `…/db/aito-accounting-demo/env/env.v2-demo/api/v2/…`. The
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

All queries go to `POST …/env/env.v2-demo/api/v2/_query`. Confirmed live shapes:

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
The response is reshaped vs v1: each hit's `related`/`condition` come back as
**stringified pseudo-syntax** (`"{ \"$and\" : [ { vendor:Bronex }, … ] }"`), and
stats are flat (`lift`, `info`, `f`, `n`) rather than nested `fs`/`ps`. The
two-stage design (discover conjunctions, then recompute exact support with a
`limit:0` count query) is unchanged; only the discovery parser adapts to strings.

**Schema / data** (env-scoped, master key):
- Create collection: `PUT …/api/v2/schema/{name}` `{"type":"collection","columns":{…}}`.
- Load: `POST …/api/v2/data/{name}/batch` with a JSON array of rows.

See `docs/notes/aito-v2-migration-feedback.md` for the full probe log and the
open items (verb mapping for `_match`/`_similarity`/`_evaluate`, analyzer
round-trip, etc.).

## Acceptance criteria

- Given the master key, a developer can run `./do` (new subcommand) to branch
  `env.v2-demo` and build the full dataset as collections, idempotently.
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
appendix describing how to run the demo against v2 (`env.v2-demo`) once parity
is reached. If v2 becomes the default, the main script is revisited then — out
of scope for this ADR.

## Out of scope

- Promoting `env.v2-demo` into master / making v2 the default demo. This ADR
  builds and proves the v2 path; the cutover is a later decision.
- Migrating `_match` (payment matching), `_similarity`, `_evaluate` (quality
  dashboard), and `_aggregate` — their v2 forms aren't yet confirmed (no
  `_query` key exists for them). These features keep running on v1 until the v2
  mapping is known. Tracked as open questions in the feedback note.
- Any change to fixture *generation* (`generate_fixtures.py`). v2 consumes the
  same fixtures; only the upload target/format changes.
- Performance tuning (optimize/backfill semantics on collections at 128k+ rows)
  beyond confirming correctness. Scale hardening is a follow-up.
