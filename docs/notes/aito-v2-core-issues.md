# Aito v2 — consolidated issues for core development

Single actionable list of everything found while migrating a real application
(an accounting demo: invoices → GL/approver prediction + `$patterns` rule mining)
from the v1 API to v2. Each item is self-contained: severity, a concrete repro,
expected vs actual, and why it matters. IDs (`V2-n`) are stable references.

> **Re-check 2026-07-14** — after the core update (rev `b97566fd`), **8 of 10
> are fixed, 1 clarified, 1 minor open.** Both P0s are resolved. See the Status
> column and the per-issue **Status** lines. Remaining: **V2-3** (403 vs 404 on a
> malformed env path) and **V2-10** (docs, unverified from here).
>
> **Round 2, 2026-08-15 (rev `7d5c48a9`)** — migrating the last three verbs
> surfaced **five new issues, two of them P0**: `_match` cannot rank
> (**V2-12**) and `recommend` silently drops tenant-scoping filters
> (**V2-13**). Both block a feature outright. See the round-2 section below.
>
> **Round 3, 2026-08-31 (rev `38a234a6`)** — first verification against a
> *current* deploy. **Every issue is now closed**: 12 fixed, 2 reclassified as
> not-a-bug (documented behaviour), 1 was our own error. Both round-2 P0s are
> resolved, which **unblocks the help drawer**. Two small new findings, both
> cosmetic. See the round-3 section at the end.

**Reproduction environment**
- Instance / db: `https://shared.aito.ai/db/aito-accounting-demo`
- Env (branched from master): `v2-demo` → base URL
  `https://shared.aito.ai/db/aito-accounting-demo/env/v2-demo/api/v2`
  (was `env.v2-demo` until the `env.` prefix became reserved — see **V2-11**).
- Auth: the master API key (env auth is database-scoped; no env-scoped key).
- Deploy under test (round 1): `/version` → built `2026-07-11`, gitRevision
  `9ea7740407204f4347ceeebc2dc7cc54ab06f02e`.
- Deploy under test (round 2): built `2026-08-15T08:46Z`, gitRevision
  `7d5c48a98c03cf090504163779919109db23d17e`.
- Deploy under test (round 3): built `2026-08-31T08:17Z`, gitRevision
  `38a234a6957f74588c2399c397380f15900bbc29` — the first re-check against a
  deploy that is actually current.
- Data: 8 collections, 220 894 rows; `invoices` = 128 000 rows, 255 customers.

**Priority summary**

| ID | Sev | Area | One-liner | Status (rev b97566fd) |
|----|-----|------|-----------|-----------------------|
| V2-1 | **P0** | predict | `predict` is segment-sensitive → flat/unstable posteriors | ✅ **Fixed** — sharp & batch-invariant after optimize |
| V2-2 | **P0** | relate `$on` | `$on` relate: no `fs`, wrong `lift`, hides exception values | ✅ **Fixed** — all three |
| V2-3 | P1 | routing | non-matching env path returns 403, not 404 (addressing trap) | ⚪ Round 3: not a bug — documented |
| V2-4 | P1 | errors | several 500s that should be 4xx (empty body, missing table, oversize) | ✅ **Fixed** — 400 / 404 / 200 |
| V2-5 | P1 | errors | validation error leaks internal Scala class name | ✅ **Fixed** |
| V2-6 | P1 | query | unknown headers / query params silently ignored | ✅ **Fixed** — errors helpfully |
| V2-7 | P1 | predict | `basedOn` featurization has no effect on `predict` | ✅ Clarified — link-field predict; errors helpfully |
| V2-8 | P2 | relate `$patterns` | `related`/`condition` returned as stringified non-JSON | ✅ **Fixed** — structured dicts |
| V2-9 | P2 | schema | `GET /schema/{t}` drops `link` / `analyzer` (not round-tripped) | ✅ **Fixed** — round-trips |
| V2-10 | P3 | docs | v2 docs lack predictive-query examples / operator ref; `/llms.txt` 404 | ✅ Round 3: **Fixed** |

What already works well (please don't regress): unified `_query`; `predict`
top-1 matches v1; `$patterns` on collections is numerically identical to v1;
cross-collection **links auto-flatten** into dotted fields (`customer_id.name`);
`_envs` branch/promote; `$not`, nested-`from` scoping, `optimize`.

---

## V2-1 — [P0] `predict` on collections is segment-sensitive

`predict` combines **per-segment** statistics rather than global ones, so its
output depends on how rows were inserted (batch/segment count) and on
`optimize` — neither of which should affect inference. v1 is invariant to both.

**Repro (no optimize, identical rows, only batch count differs):** load the same
16 000 invoices into two collections, one in 4 insert-batches, one in 80, then
`predict gl_code where {vendor:"EEE Energy Ecology Engineering Oy",
customer_id:"CUST-0000"}`:

| load | top-2 |
|---|---|
| 4 batches  | `4400 @ 0.913`, … |
| 80 batches | `4400 @ 0.668`, … |

Ground truth: this vendor is 97.8% `4400`.

**Corroborating observations**
- On the full 128 000-row collection (loaded in 128 batches) the same query
  mispredicts `1600 @ 0.19` before `optimize` and `4400 @ 0.63` after — because
  `optimize` merges segments. On a single-customer 16k collection it's already
  `4400 @ 0.93`.
- `optimize` therefore *changes* predict results (it slightly flattened one case,
  sharpened another) — a pure segment-merge must be result-neutral. Idempotent
  (opt#1 == opt#2).
- Ruled out as causes (controlled): links (native vs linked collections give
  identical predictions), and elapsed time / async indexing (t0 == t+40s).
- On the same un-optimized collection, `$patterns`/`relate` is already
  numerically identical to v1 — so the co-occurrence stats are correct and
  present; only predict's *combination* step is wrong.
- Even fully optimized, posteriors stay flatter than v1: e.g. Bronex→`1600 @
  0.466` with `6100 @ 0.432` (a near-tie that can flip top-1); v1 gives `0.881 /
  0.096`. `6100` recurs as a spurious high-scorer across unrelated vendors.

**Expected:** `predict` invariant to insert batching and to `optimize`, with v1's
calibration (concentrated on the empirically dominant value).
**Impact:** wrong/again unstable top-1 on larger collections; user-visible
confidence scores become meaningless. Blocks migrating any prediction UI to v2.

**Status (2026-07-14, rev b97566fd): ✅ Fixed.** After `optimize`, predict is
now batch-invariant and sharp: the same 16k rows loaded as 4 vs 80 batches both
give `EEE → 4400 @ 0.973` post-optimize (pre-optimize still differs, 0.786 vs
0.667 — an expected transient of an un-merged collection). The existing 128-batch
production collection now predicts `EEE @ 0.974` / `Bronex @ 0.906` at query time
(was 0.19/0.47). Matches v1's calibration. Predict-side migration unblocked.

## V2-2 — [P0] `$on` conditional relate: no `fs`, wrong `lift`, hides exceptions

Used for "why does this rule have exceptions": relate a rule's remaining features
to its output within the rule's population, via
`where: {"$on": [target, population]}`. Full writeup with tables:
`docs/notes/aito-v2-on-operator-report.md`. Three independent gaps:

- **(a) omits `fs`/counts.** The response has `related` + `lift` but no `fs`
  (`f`, `fOnCondition`), even with `select:["related","lift","fs"]`. v1 returns
  them. → no exact agree/total.
- **(b) `lift` is wrong.** Population `vendor="Dottoressa Oy" AND
  category="consulting"`, target `gl_code=5400` (base rate 815/831 = 0.981):
  `amount_band=large` has true agreement 51/53 = 0.96 → expected lift ≈ 0.98, but
  v2 returns **0.29**. `medium` (764/778 = 0.982, expected ≈ 1.00) returns
  **1.62**. A lift-thresholded diagnostic misclassifies from this.
- **(c) hides exception values.** `$on` conditions on `target = yes`, so a value
  that never co-occurs with the target has zero conditioned rows and **is not
  returned**. Population `vendor="K. Itäluoma Oy" AND category="maintenance"`,
  target `1600`: `amount_band=medium` is `0/26` (the entire exception) and is
  absent from the relate — i.e. the diagnostic can't see the thing it exists to
  find.

**Expected:** return `fs` (`f`, `fOnCondition`, `fCondition`); `lift` =
`P(value|target,pop) / P(value|pop)` (v1 semantics); and enumerate a population's
feature values including the ones with zero agreement.
**Impact:** exception diagnostics can't be built on `$on` as-is; we worked around
it by recomputing from exact counts (O(values) extra round-trips).

**Status (2026-07-14, rev b97566fd): ✅ Fixed — all three.** The K. Itäluoma repro
now returns `fs = {f:327, fOnCondition:322, fCondition:322, …}`; `lift` is correct
(large `1.083`, medium `0.023` — matches v1); and the exception value
`amount_band=medium` (0/26) is present. `related` also now comes back as a
structured dict (see V2-8). We dropped the recompute workaround — the client is a
thin `$on` wrapper again and `interpret_diagnosis` consumes the response directly.

## V2-3 — [P1] Non-matching env path returns 403 instead of 404

An env is addressed as `…/db/{db}/env/{name}/api/v2/…`. A path that doesn't match
(wrong shape, or a name that isn't an env) **falls through to the master
permission check and returns `403 "not authorized to access this resource"`**,
not a 404. `…/db/{db}/env.v2-demo/api/v2/schema` (dotted, missing `/env/`
segment) → 403; `…/env/v2-demo/…` (name without the `env.` prefix) → a correct
`404 "Env 'v2-demo' not found"`.
**Impact:** the 403 read as an auth problem and sent us hunting for a
non-existent env-scoped key for a full session. Addressing errors should 404, not
403.

**Status (2026-07-14, rev b97566fd): ❌ Still open.** The dotted path (missing the
`/env/` segment) still returns 403, not 404. Minor, but still the one addressing
trap that remains.

**Status (2026-08-31, rev 38a234a6): ⚪ Not a bug — closing.** The 403 is the auth
boundary's uniform answer for every unresolvable resource (nonexistent db, garbage
segment, unrouted path all give it; an unknown path *inside* a resolved db 404s
correctly), so 404ing here would confirm which databases exist to an unauthorized
caller. The docs now name the trap explicitly. See round 3.

## V2-4 — [P1] Several 500s that should be 4xx

- `POST /_envs` with `{}` → **500 "internal server error"** (expected 400 naming
  the required `name`).
- `DELETE /schema/{name}` on a non-existent collection → **500** (expected 404).
  Breaks idempotent "drop if exists" loaders.
- One insert batch of 16 000 rows → **500 "Request too large"** (expected 413 with
  the actual size/row limit).

**Status (2026-07-14, rev b97566fd): ✅ Fixed.** Empty `_envs` → `400 "Missing or
invalid 'name'"`; DELETE missing collection → `404 "No such table"`; the 16 000-row
insert now succeeds (`200`, limit raised).

## V2-5 — [P1] Validation error leaks an internal class name

A wrong-type `basedOn` value → `"field 'basedOn' must be of type
'Null|com.knowledgegarden.episto.common.utils.TypedJsonFormat$$anon$1@5c9…'"`.
Contrast the *excellent* unknown-field errors that enumerate the grammar
(`Expected one of from, let, where, search, get, predict, …`) — that pattern
should be the norm; leaking a Scala class name is unusable.

## V2-6 — [P1] Unknown headers / query params silently ignored

`x-aito-env`, `x-aito-environment`, `aito-env`, and `?env=` are all accepted and
ignored (the query still hits master). An unrecognized env selector should error,
not be silently dropped — otherwise a developer ships a query they believe is
env-scoped but isn't.

## V2-7 — [P1] `basedOn` has no effect on `predict`

`basedOn:["vendor"]` (should make `vendor` the sole feature → a sharp posterior)
returns the *identical* distribution to no `basedOn` and to `basedOn:[all
fields]`. So predict's feature set can't be steered — relevant to V2-1 (can't
manually restrict to the good predictors as a mitigation).

**Status (2026-07-14, rev b97566fd): ✅ Clarified — not a bug.** `basedOn` now
errors helpfully: *"basedOn applies when the predict target is a link field;
'gl_code' is not a resolvable link. basedOn names fields of the LINKED table to
use as candidate evidence…"*. So `basedOn` was never a feature-selection knob for
an ordinary predict; the original expectation was wrong. It no longer silently
no-ops.

## V2-8 — [P2] `$patterns` returns stringified, non-JSON propositions

Each hit's `related`/`condition` come back as a string, e.g.
`'{ "$and" : [\xa0{ vendor:Investra Management Oy }, { category:insurance } ] }'`
— `$and` quoted, but field/value pairs unquoted with spaced values and
non-breaking-space separators. Not parseable as JSON; every client needs a
bespoke parser. v1 returned reusable JSON objects
(`{"vendor":{"$has":"…"}}`). Prefer structured JSON. (Stats are also flat —
`lift`, `info`, `f`, `n` — vs v1's nested `fs`/`ps`; fine, just note it.)

**Status (2026-07-14, rev b97566fd): ✅ Fixed.** `related`/`condition` now come
back as structured dicts (`{"$and": [{"vendor": "…"}, {"category": "…"}]}` /
`{"gl_code": "5300"}`), directly consumable by the existing `parse_conjunction`.
We deleted the string parser.

## V2-9 — [P2] `GET /schema/{table}` drops `link` and `analyzer`

Creating a collection with `link` and `analyzer:"english"` columns succeeds and
they work (dotted-link selects resolve; presumably FTS too), but
`GET /schema/{table}` echoes the column back **without** `link`/`analyzer`
(`nullable` is kept). So you can't read back the schema you wrote, and a
"does the live schema match?" check spuriously fails. Round-trip them, or reject
if unsupported — don't accept-then-hide.

**Status (2026-07-14, rev b97566fd): ✅ Fixed.** `GET /schema/{t}` now echoes
`link` and `analyzer` back (`{"note": {"type":"Text","analyzer":"english"}, …,
"parent": {"type":"String","link":"customers.customer_id"}}`).

## V2-10 — [P3] v2 documentation gaps

The public v2 pages (`/docs/api/v2/`, `/playground/`) describe `from/where/
orderBy/select/limit` but the "Query operator reference", "Behavioral differences
from v1", and any `predict`/`recommend`/`relate` request/response examples are
absent or client-side-only. `/llms.txt` 404s. A developer (or an AI) can't learn
to write a v2 prediction from the docs alone — most of the grammar above was
reverse-engineered from error messages.

**Status (2026-08-31, rev 38a234a6): ✅ Fixed.** `/docs/api/v2/` now carries a
query-operator reference, a query-type guide, `common-errors`, `evaluation`,
`schema-design` and `environments`, all with request/response examples; `/llms.txt`
returns 200. See round 3.

---

# Round 2 — found 2026-08-15 (rev `7d5c48a9`)

Found while migrating the **remaining** verbs (`_match`, `_evaluate`,
`_recommend`) — the ones ADR 0017 had deferred because no `_query` key exists
for them. Answer: `_match` and `_evaluate` survive as their own v2 endpoints.
`_evaluate` migrated cleanly; the other two are blocked by the issues below.

| ID | Sev | Area | One-liner |
|----|-----|------|-----------|
| V2-11 | P1 | envs | `env.` prefix became reserved — a silent rename that broke every stored env path |
| V2-12 | **P0** | `_match` | `_match` returns raw `$f`, never `$p`/`$why`, and cannot rank unseen input |
| V2-13 | **P0** | `recommend` | disjunctive filters on linked fields are **silently dropped** → cross-tenant leak |
| V2-14 | P1 | schema | union branch rejects a `$text`-sourced projection at create time |
| V2-15 | P3 | schema | internal `__cache` collection listed in `GET /schema`, then 500s on query |

## V2-11 — [P1] `env.` became a reserved prefix; existing envs silently renamed

We created `env.v2-demo` (mirroring the built-in `env.master`) and stored that
name in app config, a `./do` command, an ADR, and tests. After the update every
call fails:

```
GET …/env/env.v2-demo/api/v2/schema
→ 400 "Env name 'env.v2-demo' is reserved (names may not start with '_', 'env.' or 'release.')"
```

`GET /_envs` now reports the env as **`v2-demo`** — the data survived, the name
was rewritten under us. Two problems:

1. **No migration path or warning.** A name the API itself accepted at creation
   became invalid; every stored URL broke at once. If names are being
   renamed, the old form should keep resolving (or 301), not 400.
2. **The listing is self-inconsistent.** Master still reports as `env.master`,
   i.e. with the very prefix that is now forbidden for everyone else:
   ```json
   {"envs": [{"isMaster": true, "name": "env.master"}, {"isMaster": false, "name": "v2-demo"}]}
   ```
   So the one example a developer copies is the one they may not imitate.
   Either report master as `master`, or keep the prefix legal.

**Status (2026-08-31, rev 38a234a6): ✅ Fixed — both halves.** `/env/env.v2-demo/`
resolves again (200), so stored URLs work; and `GET /_envs` now reports master as
`master`. `env.`-prefixed *creation* is still refused, which is intended — but the
docs list only `_` as reserved (see round 3, N3).

## V2-12 — [P0] `_match` returns raw counts, cannot rank, and ignores `select`

`_match` is the operator behind payment matching (bank transaction → open
invoice), one of the demo's four headline features. In v2 it is unusable.

**Repro** (`bank_transactions` 67 665 rows, linked `invoice_id` → `invoices`):

```jsonc
POST …/api/v2/_match
{ "from": "bank_transactions",
  "where": {"description": "KULJETUSLIIKE ROSENBERG-BOMAN OY VIITE 999999999 / 01.01.26",
            "amount": 10734.5},
  "match": "invoice_id", "limit": 5 }
```

**Actual** — every candidate scores 0 and the result degenerates to ID order:

```json
[{"$f": 0, "$value": "CUST-0000-INV-000001"},
 {"$f": 0, "$value": "CUST-0000-INV-000002"},
 {"$f": 0, "$value": "CUST-0000-INV-000003"}]
```

**Expected** — v1 returns a graded `$p` per candidate plus `$why`.

Three distinct defects:

1. **No probability.** Hits carry `$f` (a raw co-occurrence count), never `$p`.
   A count is not a confidence; the UI shows a match percentage.
2. **No generalization.** `$f` is non-zero *only* when the exact context was
   already seen. Feed a payment that is in the training data and the true
   invoice ranks first with `$f: 1`; feed a genuinely novel one — the actual
   use case — and **every** candidate ties at 0. That is a memorization
   lookup, not a probabilistic match.
3. **`select` is silently ignored.** `"select": ["$p", "$value", "$why"]`
   returns `$f`/`$value` anyway — no error, no `$p`, no `$why`. Requesting a
   field that isn't produced should fail loudly, not be dropped. (`_query`
   errors correctly on unknown fields; `_match` does not.)

**Impact:** payment matching cannot migrate. It stays on v1.

**Status (2026-08-31, rev 38a234a6): ✅ Fixed — all three defects.** `$p` is
graded, ranking generalizes to unseen evidence, and `select`/`$why` are honoured.
See round 3.

## V2-13 — [P0] `recommend` silently drops disjunctive filters on linked fields → cross-tenant leak

The demo's help ranking is multi-tenant: a customer may see global articles
(`customer_id = "*"`) plus their own internal ones, never another tenant's.
That is one clause:

```jsonc
"where": {"customer_id": "CUST-0000",
          "article_id.customer_id": {"$or": ["*", "CUST-0000"]}}
```

**Actual:** the linked-field clause is **discarded without error** and the
candidate pool stays unfiltered — returning other tenants' `internal` articles:

| `where` on `article_id.customer_id` | total | top hits |
|---|---|---|
| *(omitted)* | 120 | `CUST-0003-INT-04`, `CUST-0013-INT-01` |
| `"*"` (plain equality) | **20** | `APP-03`, `APP-05` ✅ honored |
| `"CUST-0003"` (plain equality) | **5** | `CUST-0003-INT-*` ✅ honored |
| `{"$or": ["*", "CUST-0000"]}` | **120** | `CUST-0003-INT-04` ❌ **dropped** |
| `{"$or": [{...:"*"}, {...:"CUST-0000"}]}` | **120** | `CUST-0003-INT-04` ❌ dropped |
| `{"$in": ["*", "CUST-0000"]}` | **120** | `CUST-0003-INT-04` ❌ dropped |

So **plain equality on a linked field is honored, every disjunctive form is
not** — and no form of `$or`/`$in` we tried works. There is no workaround.

Critically, the *same* clause works on plain `_query` against the same
collection (`total` 11 815 of 14 580, correctly filtered), so this is specific
to `recommend`, not to linked fields or to `$or` generally.

**Why it's P0:** this is a silent authorization failure. An app that correctly
expresses tenant scoping gets another tenant's private content back, with a
200 and no indication the filter was ignored. Anyone porting a multi-tenant
`_recommend` to v2 inherits the leak invisibly. Even if disjunctions on linked
fields are genuinely unsupported, the query must be **rejected**, never
silently broadened.

**Impact:** help ranking cannot migrate. It stays on v1.

**Status (2026-08-31, rev 38a234a6): ✅ Fixed.** `$or` and `$in` on a linked field
both filter correctly (120 → 25); no cross-tenant leak. Help ranking can migrate.
See round 3.

## V2-14 — [P1] union branch rejects a `$text`-sourced projection at create time

Hit on a *different* codebase (an internal CRM tool building a unified search
index over docs/contacts/deals), so it reproduces beyond this demo:

```
PUT /api/v2/schema/search_items
→ 400 {"code": "schema.create_failed",
       "message": "union branch 'from':'contacts' projects 'title' from $text
                   source column 'search_title', which does not exist in 'contacts'"}
```

The branch projects a `$text` search column that the union expects each member
to supply. Either `$text`-derived columns should be visible to union
projection, or the error should name the required column shape — as written it
says what is missing without saying what would satisfy it. Blocks that tool's
search entirely (it rebuilds the index on demand, so the feature is down).

**Status (2026-08-31, rev 38a234a6): ⚪ Not a bug — our schema error.** The real
blocker was a `nullable` `$text` source column; that restriction is lifted and the
requirement is documented. See round 3.

## V2-15 — [P3] internal `__cache` collection is listed, then 500s

`GET /schema` includes an entry the caller cannot use:

```json
"__cache": {"type": "unavailable", ...}
```

Querying it (a natural thing to do when iterating the schema listing) returns
**500**, not a 4xx. Either hide internal collections from the listing or make
them return a clean 4xx — as-is, "iterate the schema and count rows" crashes.

**Status (2026-08-31, rev 38a234a6): ✅ Fixed.** `__cache` is no longer listed, and
querying it returns `404 "__cache not found"`. See round 3.

---

# Round 3 — verified 2026-08-31 against rev `38a234a6`

The first re-check against a **current** deploy (`/version` → built
`2026-08-31T08:17Z`, gitRevision `38a234a6957f…`; every earlier round-2 finding
was measured against a stale build and could not distinguish "not fixed" from
"not deployed"). Each item below was re-run live, and — where the question was
whether the behaviour is a defect at all — checked against the published v2
docs, which have themselves grown substantially since round 1.

| ID | Was | Now | Evidence |
|----|-----|-----|----------|
| V2-3 | P1 open | ⚪ **Not a bug** — documented | 403 is the auth boundary's uniform answer for *any* unresolvable resource |
| V2-10 | P3 open | ✅ **Fixed** | operator reference, query-type guide, `common-errors`, `evaluation` all live; `/llms.txt` 200 |
| V2-11 | P1 | ✅ **Fixed** | old `env.`-prefixed URLs resolve again; `_envs` reports master as `master` |
| V2-12 | **P0** | ✅ **Fixed** — all three defects | `$p`, generalization, and `select`/`$why` all verified |
| V2-13 | **P0** | ✅ **Fixed** | `$or`/`$in` on a linked field now filter; no cross-tenant leak |
| V2-14 | P1 | ⚪ **Not a bug** — was our schema error | the nullable-`Text` restriction is lifted, and the rule is documented |
| V2-15 | P3 | ✅ **Fixed** | `__cache` hidden from `GET /schema`; querying it 404s, not 500s |
| V2-16 | P2 | ✅ **Fixed** | `x-aitoai-response-time` present on v2 |
| *evaluate baseline* | P2 | ✅ **Fixed** | `baseAccuracy` respects the tenant scope; `meanRank` agrees with v1 |

Round-1 fixes all **hold** — no regressions: V2-1 (predict sharp: EEE `4400 @
0.977`), V2-2 (`$on` returns `fs`, correct `lift`, and the zero-agreement
exception value), V2-4 (400 / 404), V2-5, V2-6, V2-8 (structured propositions),
V2-9 (`link`/`analyzer` round-trip).

## The two P0s, in detail

**V2-12 — `_match` now ranks.** The original repro, unchanged, on a payment
whose reference number appears nowhere in the data:

```json
{"from": "bank_transactions",
 "where": {"description": "KULJETUSLIIKE ROSENBERG-BOMAN OY VIITE 999999999 / 01.01.26",
           "amount": 10734.5},
 "match": "invoice_id", "limit": 5, "select": ["$p", "$value", "$why"]}
```

All three defects are gone. Hits carry a graded **`$p`** (top `2.09e-4`, tail
`3.92e-5`) instead of a flat `$f: 0`. It **generalizes** — the true invoice
(`CUST-0000-INV-000002`) ranks first from a novel reference number, on `amount`
lift `14.68` plus description tokens. And `select` is **honoured**: `$why`
comes back when asked, and an unknown column now fails loud with a 400. The
docs match the behaviour verbatim — "ranked by calibrated probability …
generalizing to evidence never seen verbatim … Honours `select` / `$why`".

**V2-13 — the cross-tenant leak is closed.** Same table, same clause:

| `where` on `article_id.customer_id` | before | now |
|---|---|---|
| *(omitted)* | 120 | 120 |
| `"*"` | 20 | 20 |
| `{"$or": ["*", "CUST-0000"]}` | **120** ❌ | **25** ✅ |
| `{"$in": ["*", "CUST-0000"]}` | **120** ❌ | **25** ✅ |

25 = the 20 global articles plus CUST-0000's own 5, and the top hits are
`CUST-0000-INT-*` — no other tenant's `internal` content. The changelog records
it as "Filters no longer dropped under a tenant scope". **This unblocks the
help drawer**: the app's existing `help_service.py` query, byte-for-byte
unchanged, returns correctly-scoped hits on v2 with the linked-field `select`
(`title` / `body` / `category` / `tags`) resolving as before.

## The two reclassifications

**V2-3 is not a bug.** The complaint was that a malformed env path 403s instead
of 404ing. Probing the boundary shows the 403 is *uniform*: a nonexistent
database, a garbage path segment, and a completely unrouted path all return the
same "not authorized" — while an unknown path **inside** a resolved database
correctly 404s. That is a deliberate don't-confirm-what-exists policy at the
auth layer, and 404ing instead would leak database existence to an unauthorized
caller. The real cost was never the status code but the lost session, and that
is now fixed where it belongs — in the docs, which spell the trap out:

```
✅  /db/{db}/env/{name}/api/v2/_query
❌  /db/{db}/env.{name}/api/v2/_query      (dot — not an env selector)
```

with "a `403` that reads fine on `master` is almost always an **addressing**
bug". Close as documented-behaviour.

**V2-14 was our own schema error.** The real blocker behind that report was a
`$text` union source declared `nullable` — and that restriction is now lifted
(a view over a nullable `Text` column creates fine). The requirement is also
documented: "The named source columns must themselves be `Text` … A non-`Text`
source is rejected — declare the field `Text` in the source schema first."
Nothing to fix in core.

## The evaluate baseline (was: metrics not v1-comparable)

`baseAccuracy` no longer ignores the `where` scope. On the demo's own query
(50 test rows, `customer_id = "CUST-0000"`):

| | v1 | v2 before | v2 now |
|---|---|---|---|
| `accuracy` | 0.98 | 0.98 | 0.98 |
| `baseAccuracy` | 0.44 | **0.1723** (global majority class) | **0.4680** |
| `meanRank` | 0.1 | 1.1 (1-based) | **0.1** |

The inflated `+80.8pp` gain is gone. A residual, harmless convention difference
remains: v1 takes the base rate over the **50-row test sample** (22/50 = 0.44),
v2 over the **training population** (7464/15950 = 0.46796). Both are honest;
they just aren't identical. The demo's own docs claiming these metrics are
"not v1-comparable" now need updating.

## Two new findings — both cosmetic, neither blocking

- **N1 — `meanRank` docs contradict the behaviour.** `evaluation-v2.md` says
  "Average position of the correct answer (**1 = always top**)", but the live
  build returns `meanRank: 0.1` at 98% accuracy — i.e. 0-based, agreeing with
  v1. The behaviour is the right one; the doc line is stale.
- **N2 — a union-projection error message got less specific.** A branch
  projecting a nonexistent `$text` source column now says *"union column
  'content' has no source in any branch (every branch's projection is
  absent)"*, which names neither the offending column nor the branch. The
  older message did: *"union branch 'from':'contacts' projects 'title' from
  $text source column 'search_title', which does not exist in 'contacts'"*.
  Worth restoring the specifics.
- **N3 (trivial) — env naming docs are incomplete.** `environments-v2.md` says
  "Names starting with `_` are reserved"; the API actually rejects `_`, `env.`
  **and** `release.` (and says so in its error). Match the doc to the error.

**Method note.** Every probe ran against the `v2-demo` env, and the three
scratch collections created for the V2-14 repro were deleted afterwards
(`GET /schema` confirmed clean). Nothing touched master.

---

*Compiled 2026-07-13 during the v2 migration (branch `feat/0017-aito-v2-migration`);
round 2 added 2026-08-15; round 3 verified 2026-08-31. Ongoing log:
`docs/notes/aito-v2-migration-feedback.md`; `$on` deep-dive:
`docs/notes/aito-v2-on-operator-report.md`.*
