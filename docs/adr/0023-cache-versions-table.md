# 0023. A cache-versions table, so containers notice a rebuild

**Date:** 2026-09-19
**Status:** accepted

## Context

ADR 0022 added `POST /api/cache/invalidate`, which works but has to be
*called*. Someone must remember, after every `./do precompute-v2`, that a
running container is still serving what it read before — and that someone
forgot four times in three sessions. The clearest case: after promoting
the settlement data and rebuilding all 20 tenants, the site served
`AVARN SECURITY OY` while the database said `AVARN HOLDING OYJ`. Matching
was correct, every response a 200, the page simply a build behind.

A manual lever fixes the symptom. The container should notice by itself.

It cannot notice by polling the payloads: a single keyed row lookup in
`precompute_entries` measured 0.82 s, 0.86 s and 5.23 s — about what
reading a whole payload costs, on a table of 285 rows carrying large
`Text` blobs. Polling per key, per request, is not an option. It needs
one small row that says whether anything changed.

A dedicated table is far cheaper than that measurement suggested. Reading
every row of `cache_versions` measured **0.21 s, 0.25 s, 0.21 s** live,
and a full poll including the comparison took 0.07 s warm. The expensive
part was never the query, it was the payload table it was run against.

## Decision

A `cache_versions` table: one row per **scope**, holding the epoch second
at which that scope was last written.

```
scope    String   "table:invoices", "precompute:matching_pairs"
version  Int      unix seconds of the write
```

- **Writers bump.** `./do precompute-v2` bumps `precompute:<view>` for
  each view it writes. `./do v2-build` bumps `table:<name>` for each table
  it loads. Both already know exactly what they touched.
- **The app polls**, on a background thread, every `CACHE_WATCH_SECONDS`
  (default 60, `0` disables). One query returns every row — ~0.2 s on the
  live table — so the cost is one small query per minute per container and
  **zero added request latency**: the check never runs on the request
  path, it runs on a daemon thread.
- **Invalidation is scoped.** A changed `precompute:<view>` drops only the
  L1 entries for that view, across customers. A changed `table:<name>`
  drops everything, because every derived view depends on the tables.

### Why a version per scope rather than one global counter

A global counter would drop all 20 tenants' payloads because one view of
one tenant was rebuilt, and the next request for each would recompute
live at 7–15 s. Scoping keeps a partial rebuild partial. The two writers
already know their scope, so this costs nothing to produce.

### What this does not do

It does not make the *first* container to notice cheap — it still re-reads
L2 for the dropped keys. It makes the notice automatic, which is the part
that was missing. And it keeps the manual endpoint from ADR 0022, because
a poll interval is a delay and sometimes you want it now.

## Aito usage

One `_query` returning all rows of a small table, once a minute. Writes go
through the same delete-then-insert upsert `precompute_store.put` uses, on
the same client, for the same reason: `cache_versions` is a plain table on
master, shared by both API generations, and what separates v1 from v2 is
the key namespace rather than the connection.

**Promote replaces it.** `cache_versions` lives in the database, so
promoting an environment swaps in that branch's copy — exactly as happens
to `precompute_entries` today. A promote should therefore be followed by a
precompute run, which is already true and already the documented order.

## Acceptance criteria

- After `./do precompute-v2`, a running container serves the new payloads
  within `CACHE_WATCH_SECONDS` without a restart or a manual call.
- Rebuilding one view does not drop the L1 entries of the others.
- With `CACHE_WATCH_SECONDS=0` no thread starts and behaviour is exactly
  as before.
- An unreachable Aito during a poll leaves the caches alone and does not
  kill the thread.

## Verified end to end

Against live Aito, with three payloads pinned in L1 and a precompute run
that rebuilt only `matching_pairs`:

```
L1 before: CUST-0000:matching_pairs, CUST-0001:matching_pairs, CUST-0000:rules_candidates
bump       precompute:matching_pairs
poll       0.07s   changed = ['precompute:matching_pairs']
L1 after : CUST-0000:rules_candidates
second poll 0.12s  changed = []
```

The rebuilt view was dropped for both customers, the view that was not
rebuilt was kept, and steady state is a no-op.

## Demo impact

None on the demo path. It removes a manual step from the operational one.

## Out of scope

- Invalidating another container's cache synchronously. Each polls for
  itself; they converge within the interval.
- Versioning anything that is not a cache (schema migrations, fixtures).
