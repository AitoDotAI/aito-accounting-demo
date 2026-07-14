# Aito v2 — consolidated issues for core development

Single actionable list of everything found while migrating a real application
(an accounting demo: invoices → GL/approver prediction + `$patterns` rule mining)
from the v1 API to v2. Each item is self-contained: severity, a concrete repro,
expected vs actual, and why it matters. IDs (`V2-n`) are stable references.

> **Re-check 2026-07-14** — after the core update (rev `b97566fd`), **8 of 10
> are fixed, 1 clarified, 1 minor open.** Both P0s are resolved. See the Status
> column and the per-issue **Status** lines. Remaining: **V2-3** (403 vs 404 on a
> malformed env path) and **V2-10** (docs, unverified from here).

**Reproduction environment**
- Instance / db: `https://shared.aito.ai/db/aito-accounting-demo`
- Env (branched from master): `env.v2-demo` → base URL
  `https://shared.aito.ai/db/aito-accounting-demo/env/env.v2-demo/api/v2`
- Auth: the master API key (env auth is database-scoped; no env-scoped key).
- Deploy under test: `/version` → built `2026-07-11`, gitRevision
  `9ea7740407204f4347ceeebc2dc7cc54ab06f02e`.
- Data: 8 collections, 220 894 rows; `invoices` = 128 000 rows, 255 customers.

**Priority summary**

| ID | Sev | Area | One-liner | Status (rev b97566fd) |
|----|-----|------|-----------|-----------------------|
| V2-1 | **P0** | predict | `predict` is segment-sensitive → flat/unstable posteriors | ✅ **Fixed** — sharp & batch-invariant after optimize |
| V2-2 | **P0** | relate `$on` | `$on` relate: no `fs`, wrong `lift`, hides exception values | ✅ **Fixed** — all three |
| V2-3 | P1 | routing | non-matching env path returns 403, not 404 (addressing trap) | ❌ Open — still 403 |
| V2-4 | P1 | errors | several 500s that should be 4xx (empty body, missing table, oversize) | ✅ **Fixed** — 400 / 404 / 200 |
| V2-5 | P1 | errors | validation error leaks internal Scala class name | ✅ **Fixed** |
| V2-6 | P1 | query | unknown headers / query params silently ignored | ✅ **Fixed** — errors helpfully |
| V2-7 | P1 | predict | `basedOn` featurization has no effect on `predict` | ✅ Clarified — link-field predict; errors helpfully |
| V2-8 | P2 | relate `$patterns` | `related`/`condition` returned as stringified non-JSON | ✅ **Fixed** — structured dicts |
| V2-9 | P2 | schema | `GET /schema/{t}` drops `link` / `analyzer` (not round-tripped) | ✅ **Fixed** — round-trips |
| V2-10 | P3 | docs | v2 docs lack predictive-query examples / operator ref; `/llms.txt` 404 | ⏳ Not re-verified |

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

---

*Compiled 2026-07-13 during the v2 migration (branch `feat/0017-aito-v2-migration`).
Ongoing log: `docs/notes/aito-v2-migration-feedback.md`; `$on` deep-dive:
`docs/notes/aito-v2-on-operator-report.md`.*
