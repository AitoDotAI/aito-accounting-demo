# Aito v2 migration — running feedback log

Living log of **product issues, doc gaps, and improvement ideas** discovered
while migrating the accounting demo from the Aito v1 API to v2
("query2" unified query + "rep2" environments). Started 2026-07-11 on branch
`feat/0017-aito-v2-migration`.

This is deliberately a *feedback* document aimed at the Aito core/docs team,
not an ADR. The ADR for the migration itself lives at
`docs/adr/0017-aito-v2-migration.md` (to be written once the approach is
confirmed). Add dated entries as we go; promote confirmed decisions to the ADR.

Severity tags: **[blocker]** stops the migration · **[friction]** costs time /
readability · **[docs]** documentation gap · **[idea]** enhancement request ·
**[question]** unresolved, needs Aito-team input.

---

## What v2 is (from https://aito.ai/docs/api/v2/, first pass 2026-07-11)

- **Unified query endpoint.** One `POST /api/v2/_query` replaces the v1 verb
  endpoints (`_search`, `_predict`, `_recommend`, `_relate`, `_match`,
  `_similarity`, `_evaluate`, `_aggregate`, `_batch`). This is "query2" — the
  new query representation.
- **First-class environments ("rep2").** `GET/POST /api/v2/_envs`,
  `DELETE /api/v2/_envs/{env}`, `POST /api/v2/_envs/{env}/promote` — branch an
  environment, work in it, promote to master. This is the native mechanism for
  the "separate aito-env" we want for the v2 demo.
- **Schema plan/apply workflow.** `POST /api/v2/schema/{table}/_plan` then
  `_apply` — migration-style schema changes (vs v1's direct `PUT /schema`).
- **New data ops.** `POST /api/v2/data/{table}/_backfill`,
  `POST /api/v2/data/_modify`, plus single + `batch` insert.
- **Same base host style.** URLs stay `https://<host>/db/<name>/api/v2/...`
  (the `/db/{name}` "collectiondb" path this instance already uses).
- Docs label v2 **beta**; production users are pointed back to v1.

---

## Query2 grammar (confirmed live on shared.aito.ai, 2026-07-11)

v2 is **live on `shared.aito.ai/db/aito-accounting-demo/api/v2`** and the
existing v1 API key authenticates against it. Probed directly (curl).

**Unified endpoint:** `POST /api/v2/_query`. A 400 from an unknown field leaked
the full top-level grammar:

```
from, let, where, search, get, predict, recommend, goal,
relate, basedOn, orderBy, select, offset, exclusiveness, limit, config
```

Confirmed behaviors:
- **`predict` survives as a top-level key.** `{"from","where","predict":"gl_code"}`
  works under `_query`. But the **response shape changed**: predicted value is
  now in **`$value`**, not v1's `"feature"`:
  - v1: `{"$p":0.91, "feature":"4400", "$why":{...}}`
  - v2: `{"$p":0.172, "$value":"4400"}`
  Result envelope is `{offset, total, hits:[...]}` (total = candidate count).
- **`relate`, `recommend` survive** as top-level keys (untested shape yet).
  `search` is FTS, `get` (untested), `goal` pairs with `recommend`.
- **`basedOn` is a featurization spec, NOT env selection** — it takes
  `$numeric`, `$patterns`, or a field-name array (error:
  *"unknown featurizer 'env' (expected $numeric or $patterns…)"*).
- **`config`** accepts only `{ai, calibrate}` sub-fields.
- **v2 auto-flattens linked columns** into dotted-path fields in `_query` hits:
  `customer_id.name`, `vendor_business_id.industry`, `processor.supervisor_id`.
  Nice for readers, but changes response parsing vs v1.

**Env branching** (`_envs`) confirmed working:
- `GET /api/v2/_envs` → `{envs:[{name,isMaster}]}`.
- `POST /api/v2/_envs` with body `{"name":"<x>"}` branches off master →
  `{"basedOn":"env.master","name":"<x>","status":"created"}`. Accepts arbitrary
  names (no `env.` prefix enforced — we used `env.v2-demo` to match `env.master`).
- `DELETE /api/v2/_envs/<name>` → `{status:"deleted"}`.
- Created **`env.v2-demo`** (branched from `env.master`) for this migration.

## Env addressing — RESOLVED (2026-07-12, via Aito-team routing trace)

The 403 was an **addressing bug, not auth**. Facts, now confirmed live:
- **There is no env-scoped key.** Env auth is *database*-scoped; the master key
  authorizes every env under the db. Branching returns no key because there is
  nothing to mint. Use the master key for reads, queries, and writes (incl.
  `PUT`-ing collections) in any env. (Aito source refs given: `ApiSupport.scala`
  auth wrapper doesn't see the env name; `EnvAdminApiSupport.scala` — env mgmt
  is database-scoped.)
- **The env goes in the path as `env` + the full env name, as separate slash
  segments:**
  `https://shared.aito.ai/db/aito-accounting-demo/env/env.v2-demo/api/v2/…`
  The dotted form I first tried (`…/env.v2-demo/api/v2/…`, no `env/` segment)
  never matches the route and falls through to the master permission check → the
  misleading 403. Note the name segment is the **full** `env.v2-demo` (the
  `env.` is part of the stored name); `…/env/v2-demo/…` → *"Env 'v2-demo' not
  found"*.
- Verified: `GET …/env/env.v2-demo/api/v2/schema` → 200; `_query` → 200 with the
  branched data (128000 rows); and a collection created in the env is **absent
  on master** (*"No such table"*) — true isolation.
- `/version` (at the instance root `https://shared.aito.ai/version`, not under
  `/db/…/api/v2`) confirms deploy: built 2026-07-11, gitRevision `9ea7740`.

**[friction/idea]** The 403 on a fall-through path is a debugging trap: a
non-matching env path should 404 ("Env '…' not found", like the slash form
does), not 403 ("not authorized"). The 403 sent me hunting for a nonexistent
env key for a whole session. Fall-through-to-master-then-403 conflates
addressing errors with auth errors.

## Collection workflow — CONFIRMED live in `env.v2-demo` (2026-07-12)

Full create → load → mine loop verified with a throwaway `_probe_col`:
- **Create:** `PUT …/api/v2/schema/{name}` body
  `{"type":"collection","columns":{"vendor":{"type":"String"}, …}}` →
  `{"status":"created","type":"collection"}`. Types: String/Text/Decimal/Int/Boolean.
- **Load:** `POST …/api/v2/data/{name}/batch` with a **plain JSON array** of row
  objects → `{"status":"inserted","count":N}`. (Single-row: `POST …/data/{name}`.)
- **Query/predict:** work as on legacy tables (predict value in `$value`).
- **`$patterns`:** WORKS on the collection (the 501 is legacy-tables-only). Same
  request shape as v1 (`{"$patterns":{"$related":{relate,k,to}}}`).

**[migration-note] v2 `$patterns` response is reshaped vs v1.** Each hit:
```
{ "related": "{ \"$and\" : [ { vendor:Bronex }, { category:software } ] }",
  "condition": "{ gl_code:1600 }",
  "lift": 1.95, "info": 0.83, "f": 20, "n": 40.0 }
```
- `related` / `condition` are **stringified pseudo-syntax** (unquoted values,
  not JSON) — v1 returned real JSON objects (`{"vendor":{"$has":"Bronex"}}`).
  `discover_conjunctions` / `parse_conjunction` need a new parser (or, better,
  Aito returns structured JSON — see friction below).
- Stats are **flat** (`lift`, `info`, `f`, `n`); v1's nested `fs`/`ps` (and
  crucially `fOnCondition`, `fCondition`) are gone. The demo's two-stage design
  (discover, then exact `_search` counts) already recomputes support, so this is
  survivable — but any client relying on `fs.fOnCondition` from `$patterns`
  directly will break.
- `select:["related","condition","lift","fs","ps"]` silently returned
  `lift,info,f,n` regardless — the `fs`/`ps` selectors were dropped, not errored.

**[friction]** Returning `related`/`condition` as a stringified non-JSON
proposition forces every client to parse a bespoke mini-language. v1's JSON
objects were directly reusable as query propositions. Strongly prefer structured
JSON in the v2 response.

### [confirmed + friction] collection links/nullable work; schema GET doesn't round-trip
Created a 2-collection setup with `link`, `analyzer:"english"`, and
`nullable:true`. All accepted (200). A `select:["parent.pname"]` query **resolved
the linked value** (`"Acme"`) — so **links are functional in v2 collections**
(same auto-flatten as legacy tables). `nullable` round-trips. **But
`GET /schema/{name}` silently omits `link` and `analyzer`** from the echoed
schema (`note` came back as bare `{type:Text}`, `parent` lost its `link`), even
though they're functionally applied. You cannot read back the schema you wrote →
schema introspection/verification is unreliable, and a CI "does the schema match"
check would spuriously fail. `link`/`analyzer` should either round-trip or be
rejected if unsupported — not accepted-then-hidden. (Analyzer's *functional*
application still to be confirmed via a `$match` FTS query during the build.)

Net: the v2 collection schema is a near-mechanical translation of the existing
`data_loader.SCHEMAS` — `type:"table"` → `type:"collection"`, columns/links/
nullable carry over unchanged.

### [milestone] predict + `$patterns` parity confirmed on real data (2026-07-12)
Thin slice: loaded CUST-0000's 16 000 invoices into a temporary
`invoices_v2_slice` **collection** in `env.v2-demo` (native columns, links
stripped) and compared to the live v1 API scoped to the same customer:
- **predict `gl_code`** (`vendor="EEE Energy…"`): both rank `4400` #1
  (v2 $p 0.934 via `$value`, v1 $p 0.973 via `feature`). Same top-1; the $p gap
  is population (slice = 1 customer's 16k rows vs v1's full 128k model), not a
  shape bug.
- **`$patterns` for `gl_code=4400`**: the headline rule is **identical** —
  `vendor="EEE Energy…" ∧ amount_band="medium" ∧ category="supplies"`, **lift
  2.09, f 3383** in both. (v2 also surfaced a 2nd Kardex rule v1 didn't return at
  limit 5 — ordering/limit nuance, not a discrepancy.)
Conclusion: the v2 collection path reproduces v1's predictive results. Approach
validated end-to-end; `AitoV2Client` + collection create/load exercised live.

### [confirmed] DELETE does not enforce link integrity (good)
The full build dropped all 8 legacy tables in `env.v2-demo` child-first with no
errors, even though other legacy tables still in the env (`prediction_log`,
`rule_revisions`) `link` to `customers`. So v2 links are value references, not
enforced FKs at delete time — a drop-and-recreate migration doesn't need a
strict topological order or a full-env wipe. (The auto-guard did flag the raw
`curl -X DELETE`, but the Python loader's deletes ran fine once the destructive
build was explicitly authorized.)

### [milestone] Full v2 build verified — parity achieved (2026-07-12)
Built all 8 fixture tables as same-named collections in `env.v2-demo`
(220 894 rows, real names, legacy tables dropped). `./do v2-build --reset`.
Verification (`v2_verify.py`) — **ALL PASS**:
- Row counts match fixtures (invoices 128000, bank_transactions 67665, …).
- **Links resolve across collections**: `customer_id.name` → "Tornio Retail Oy Ab",
  `processor.supervisor_id` → "CUST-0000-EMP-0018".
- **predict** top-1 matches v1 (EEE → 4400).
- **`$patterns`** identical to v1 (lift 2.089, f 3383), nested-`from` customer
  scoping works on collections.

### [core-side BUG] v2 predict is segment-sensitive → flat/unstable posteriors
**Root cause, proven.** v2 `predict` on a collection combines *per-segment*
statistics instead of global ones, so its output depends on how rows were
batched at ingest — an implementation detail that must not affect inference.

Controlled experiments (temp collections of CUST-0000's 16k invoices; full probe
log in `docs/verification/`-style scratch, summarized here):
1. **Batch count changes predict** (identical rows, identical query, NO optimize):
   | load of the same 16k rows | EEE (→4400) | Bronex (→1600) |
   |---|---|---|
   | 4 insert-batches | 4400 @ **0.913** | 1600 @ **0.616** |
   | 80 insert-batches | 4400 @ **0.668** | 1600 @ **0.80**, 4400 @ 0.146 |
   Batching is an ingest detail; changing it must not move inference. It does.
2. **Links: no effect.** `native`-only vs links-`intact` collections give
   *identical* predictions at every stage. (Rules out linked-column featurization.)
3. **Async/time: no effect.** t0 == t+40s with no optimize (rules out background
   indexing settling).
4. **`optimize` changes predict, and is NOT result-neutral** — because it *merges
   segments*, and predict depends on segment count. On the 16k collection it
   slightly *flattened* (EEE 0.934→0.909); on the 128-batch full collection it
   *sharpened* EEE (0.19→0.63). Direction varies; the invariant (predict output
   independent of segmentation) is simply violated. Idempotent (opt#1==opt#2).

**Consequences for the migration / demo:**
- The full production collection (128k rows in 128 batches → many segments) shows
  the worst flatness: EEE mis-predicted `1600 @ 0.19` before optimize; `4400 @
  0.63` after — still far from v1's `4400 @ 0.97`. Bronex ends at `1600 @ 0.466`
  with `6100 @ 0.432` (a near-tie that could flip top-1). v1 is sharp and
  segment-invariant.
- `relate`/`$patterns` on the *same* collection is byte-identical to v1 — so the
  stats exist and are correct; only predict's *combination* step is wrong. A dev
  testing only relate would never catch this.
- **The loader's `optimize` step is a mitigation, not a fix** — it reduces
  segment count so predict is less-bad, but the real fix is core-side: predict
  must combine global statistics, invariant to batching and optimize.

**For Antti / core team:** predict combination is per-segment, not global.
Expected: predict(collection) invariant to insert batching and to `optimize`,
matching v1's calibration.

### [confirmed] `optimize` exists and is idempotent
`POST /data/{name}/optimize` → `{}` (200), synchronous enough that effects are
visible on the next query; running it twice yields identical predict output. The
v2 loader runs it after load (`AitoV2Client.optimize` + `optimize_collections`)
as the mitigation above. Also: a single insert batch of 16k rows → 500 "Request
too large" (should be 413 with the actual size limit).

### [confirmed] `basedOn` does not affect predict on this build
`basedOn:["vendor"]` (should make vendor the sole feature → very sharp) returns
the *identical* distribution to no-`basedOn` and to `basedOn:[all fields]`. So
predict's feature set can't currently be steered via `basedOn` — relevant to the
flatness above (can't manually restrict to the good predictors).

### [friction] `DELETE /schema/{name}` on a non-existent collection → 500
Returns *"internal server error"* (HTTP 500) instead of 404. Makes idempotent
"drop if exists" loader logic awkward — can't distinguish "didn't exist" from a
real failure by status. (v1's DELETE returned a clean 404 the loader keys off.)

### [milestone] Rule mining ports to v2 as a drop-in — and improves (2026-07-13)
`AitoV2Client` was made interface-compatible with the v1 client for rule mining
(`search`, `relate_patterns(where_filter=…)`), and it **normalizes v2's
stringified `$patterns` response back to the v1 `{field:{"$has":v}}` dict shape**
(`parse_pattern_proposition`, tested in `tests/test_aito_v2_client.py`). Result:
`rulemining_service.mine_rules` runs **completely unchanged** with a v2 client
passed in — zero edits to the service, zero risk to v1.

Comparing `mine_rules(v1)` vs `mine_rules(v2)` for CUST-0000 (same data, exact
counts recomputed identically):
- v1: 14 rules (9 strong), coverage 44.3%. v2: **41 rules (34 strong), coverage
  77.2%**.
- v2 **covers every v1 rule** (same vendor/GL/support; clause order differs, so
  naive string-equality overlap looked like 1) and adds many more vendors.
- v2 **refines weak→strong** using the amount_band conjunction the collection
  `$patterns` now discovers: e.g. Bronex `144/186` (77%, review) →
  `144/145` (99%, strong) by adding `amount_band="large"`; Dottoressa consulting
  and Ville Saarinen likewise sharpen.
So migrating rule mining to v2 is a net **quality gain**, not just parity —
consistent with the improved collection-side pattern miner.
- **Residual:** v2 surfaces a few more marginal weaks (e.g. `Tapani Laine
  3/324` — 0.9% precision but lift>1 because the approver is globally rare).
  They're correctly *flagged* weak, but MIN_SUPPORT=3 alone lets near-zero-
  precision rules through; a min-precision floor would be cleaner. Pre-existing
  discovery-threshold nuance, not v2-specific.

### [deferred] v2 diagnostics ($on) needs count recomputation
The ADR 0015 drill-down uses `relate_features` (an `$on` conditional relate) and
reads `fs.f` / `fs.fOnCondition` for exact agree/total. On v2 collections the
`$on` query **works and returns `related` + `lift`, but omits `fs`/counts**
entirely (even with `select:["...","fs"]`). So `interpret_diagnosis` would drop
everything (total=0). Porting diagnostics therefore needs the agree/total counts
recomputed with exact `_query limit:0` calls (the same two-stage trick mining
uses), rather than read from the relate response. Deferred to a follow-up; core
mining is the higher-value port and is done.

## Open questions / decisions needed

- **[decision] Collection naming for the full build.** `env.v2-demo` was branched
  from master, so it already holds the *legacy* tables (`invoices`, `customers`,
  …, ~128k rows). Building same-named collections requires **dropping those
  legacy tables in the env first** (isolated + reversible by re-branching, but a
  destructive op the auto-guard flags). Alternative: suffix collections (`_v2`),
  non-destructive but forces link targets and app queries onto suffixed names.
  Recommend dropping-and-replacing in the isolated env for a clean migration.
- **[question]** v2 mapping for verbs absent from the grammar: **`_match`**
  (payment matching), `_similarity`, `_evaluate` (quality dashboard),
  `_aggregate`, `_estimate`. None appear as `_query` keys — need their v2 form
  (possibly `recommend`+`goal` for match, `orderBy $similarity`, etc.).

---

## Issues & ideas

### [update] `$why` IS live in v2 — but reshaped
Contrary to the playground warning, `predict` with `$why` in `select` returns a
structured explanation on the live build. But the **shape changed**: v2 `$why`
is a nested factor *tree* (`{type:"product", factors:[{type:"baseP"...},
{type:"normalizer", name:"exclusiveness"...}, {type:"calibration",
name:"support-tempering(auto)"...}]}`), not v1's flatter proposition list. The
frontend's highlight/why rendering (invoice coding, form-fill) must be rewritten
against the new tree. Still need to confirm the `{"$why":{"highlight":{...}}}`
span form (used for Text-field token highlighting) survives.

### [architecture] v2 has TWO table kinds: "collections" vs "legacy tables"
This is the central migration fact. `POST _query` with `$patterns` on the
existing (v1-uploaded) tables returns **HTTP 501**:
*"relate $patterns on the v2 endpoint is supported on collections only — use
/api/v1/_relate for legacy tables"*. So:
- **Legacy tables** (everything currently in this db, all `type:"table"`):
  v2 supports basic query, `select`, `where`, and `predict` (+`$why`). It does
  NOT support `relate`/`$patterns`.
- **Collections** (the new v2 native type, `/docs/api/v2/collectiondb/`): the
  full v2 feature set, including `$patterns`.
Therefore migrating this demo is not "point the client at /api/v2" — it's
**rebuilding the dataset as v2 collections** in the env. That is what "set up v2
in a separate env" concretely means.

Mechanics learned live:
- **Create** a collection: `PUT /api/v2/schema/{name}` (docs: "Create new table").
- **Evolve** an existing collection: `POST /api/v2/schema/{name}/_plan` then
  `_apply`. `_plan` on a non-existent name → *"Table '…' not found"*, so plan is
  change-planning on an existing collection, not creation.
- v2 column types (from `GET /api/v2/schema/invoices`): `String`, `Text`,
  `Decimal`, `Int`, `Boolean`. (Link/relationship representation in v2 schema
  not yet confirmed — queries auto-flatten linked columns, but the table's v2
  schema GET doesn't surface the link defs. TBD.)

### [resolved] `$patterns` request shape is the SAME as v1
After the core update (2026-07-12) the error became actionable:
*"expected a field-name array or a {'$related': {relate, k, to}} wrapper"* — i.e.
the exact v1 shape `{"relate":{"$patterns":{"$related":{relate,k,to}}}}`. So no
query-shape change for rule mining; it only needs the data to live in a
collection. (Good example of the actionable-error pattern the DX should adopt
everywhere — see the error-quality item above.)

### [blocker] v2 `relate` shape is undocumented and my v1 shapes don't work
Rule mining + diagnostics (ADR 0014/0015) is built on `_relate` + `$patterns` +
`$on`. Under v2 `_query`:
- `{"relate": ["vendor","category","amount_band"], "where":{"gl_code":"1600"}}`
  is *accepted* but returns `total:0, hits:[]` for a value that has thousands of
  rows — so either the shape is wrong or `relate` isn't wired the same way.
- The v1 `{"relate":{"$patterns":{"$related":{...}}}}` shape **400s**:
  *"field 'relate' must be of type 'Null|…TypedJsonFormat…'"*.
Need the v2 `relate` / `$patterns` / `$on` request shape from the Aito team (or
docs) before the rule-mining feature can migrate. This is the single biggest
migration blocker for this demo.

### [blocker] v2 beta build is missing operators the demo depends on
Source: v2 playground page — *"Some documented operators ($search FTS, $why,
numeric ranges, $has, _relate) are not yet live on this build."*
The accounting demo relies on all of these:
- `$why` — prediction explanations / highlight spans (invoice coding view,
  smart form-fill). Core to the demo's "explainable AI" story.
- `_relate` + `$patterns` + `$has` — the entire rule-mining + diagnostics
  feature (ADR 0014, 0015).
- numeric ranges — amount-based filtering throughout.
- `$search` FTS — description matching.
Need to confirm whether these are (a) not-yet-implemented in the beta build but
planned, or (b) reshaped under a different v2 spelling. Migration of predict /
rule-mining is blocked until `$why` and `_relate`/`$patterns` land or their v2
equivalents are documented.

### [friction] error messages leak internals / are unhelpful
- `POST /api/v2/_envs` with `{}` → **HTTP 500 "internal server error"** instead
  of a 400 naming the required `name` field.
- A wrong-type `basedOn` value → *"field 'basedOn' must be of type
  'Null|com.knowledgegarden.episto.common.utils.TypedJsonFormat$$anon$1@5c9…'"*
  — leaks an internal Scala class name instead of the accepted shape.
These make the API hard to learn without server-side source access. Field
errors that *do* enumerate options (e.g. the unknown-field errors that list the
grammar) are excellent — that pattern should be the norm everywhere.

### [friction] unknown headers / query params are silently ignored
`x-aito-env`, `x-aito-environment`, `aito-env`, and `?env=` are all accepted and
ignored (query still returns master). Per this project's own prime directive
("never silently filter/discard unexpected data"), an unrecognized env selector
should error, not be dropped — silently ignoring it is how a developer ships a
query they think is scoped to a branch but isn't.

### [idea] auto-flattened linked columns are a nice v2 win
`_query` returns joined columns as dotted paths (`customer_id.name`,
`vendor_business_id.industry`) with no explicit join in the request. For this
demo it removes a chunk of client-side denormalization. Worth calling out in the
"behavioral differences from v1" docs (currently that section is empty).

### [docs] v2 reference pages don't render predictive query examples
The public v2 docs (`/docs/api/v2/`, `/playground/`) describe `from/where/
orderBy/select/limit` but the "Query operator reference", "Behavioral
differences from v1", and any predict/recommend/relate examples are either
behind client-side rendering or absent. An outside developer (or an AI reading
the page) can't currently learn how to write a v2 prediction from the docs
alone. An `llms.txt` for v2, or server-rendered examples, would fix this —
`/llms.txt` currently 404s.

---

## Log

- **2026-07-11** — Branch `feat/0017-aito-v2-migration` created. First pass over
  v2 docs; captured endpoint map and the operator blocker.
- **2026-07-11** — Confirmed v2 live on `shared.aito.ai` with the existing key.
  Reverse-engineered the Query2 grammar by probing (see grammar section):
  `predict` works under `_query`, value moved `feature` → `$value`, linked
  columns auto-flatten. Branched `env.v2-demo` off master via `_envs`. **Blocked
  on the env-targeting question** — queries only hit master; need Aito-team
  confirmation on whether/how a branched env is queryable before wiring the
  demo's config. Logged 6 product/DX + 2 doc issues.
- **2026-07-12** — After a core update: `$patterns` error became actionable and
  revealed the shape is identical to v1 — BUT `$patterns`/`relate` on the legacy
  tables returns **501 "supported on collections only"**. Pivotal: v2 splits
  tables into **collections** (full features) vs **legacy tables** (query +
  predict only). Migration = rebuild the dataset as collections
  (`PUT /schema/{name}`) in `env.v2-demo`. Env path **still 403** with the master
  key — the env-scoped key now blocks BOTH querying the env AND writing
  collections into it. Hard-blocked on that key to proceed.
- **2026-07-12** — Env "wall" resolved (Aito-team routing trace): no env key
  exists (master key is env key), and the 403 was an addressing bug — env path
  is `/db/{db}/env/env.v2-demo/api/v2/…` (separate `env/` + full-name segments).
  Now fully unblocked. Verified the whole v2 collection loop in the env:
  create (`PUT /schema` type:collection) → batch load (`POST /data/{name}/batch`,
  JSON array) → `$patterns` mines it (no 501). Isolation confirmed (probe
  collection absent on master). Logged the reshaped v2 `$patterns` response
  (stringified `related`/`condition`, flat stats) as the main client-side
  adaptation. Migration is de-risked end-to-end; next is the actual build
  (ADR 0017 → collections rebuild + client v2 path + response parsing).
