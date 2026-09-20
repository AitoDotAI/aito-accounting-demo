# 0022. Reload caches without a redeploy

**Date:** 2026-09-18
**Status:** accepted

## Context

`precompute_store` keeps three layers: an in-process dict (L1), an Aito
`precompute_entries` table (L2), and a bootstrap JSON file (L3). L1 is
populated on first read and **pinned for the lifetime of the process** —
there is no TTL, because a precompute payload is immutable for a given
build.

It is not immutable across builds. Rebuilding the precompute writes L2,
and a running container keeps serving L1 from before the rebuild. The
only way to pick it up is to restart the container.

That cost four separate round trips in the 2026-09-15..18 sessions. The
last one was the clearest: after promoting the settlement-entity data and
rebuilding all 20 tenants, the site still served the previous names —

```
prod:      AVARN SECURITY OY  Saaja  VIITE 901256128     (0.27s, an L1 hit)
database:  AVARN HOLDING OYJ  Saaja  VIITE 901256128
```

Nothing was broken: matching was correct, every response a 200. The page
was simply a build behind, and nothing in the running system could say so.

`precompute_store.invalidate()` already exists and does exactly the right
thing. It was never reachable over HTTP.

## Decision

Expose `POST /api/cache/invalidate`, authenticated with a shared secret.

### Authenticated, and absent by default

This is a public demo. Dropping L1 makes the next request recompute, and a
cold tenant costs 7–15 s of Aito queries — so an open endpoint is a way to
make the demo expensive on request.

The secret comes from `ADMIN_TOKEN`. When it is **unset the route returns
404**, the same as any unknown path: a clean checkout exposes no
administrative surface at all, and a scan cannot tell the endpoint from a
typo. When it is set, a wrong or missing token is 401.

Comparison uses `hmac.compare_digest`. The token is never logged and never
echoed.

### What it drops, and what it deliberately does not

- `precompute_store.invalidate()` — the pinned per-customer payloads.
- `cache.drop_local()` — new, and the reason it is new: `cache.clear()`
  **deletes and recreates the Aito `cache_entries` table**, which is
  shared L2 state that other processes are reading. Invalidating a local
  copy must not destroy everyone's. `drop_local()` clears the in-process
  dict only.

L2 and L3 are untouched. The next request re-reads L2, which is the
freshly written precompute — that is the whole point.

### The policy lives outside `app.py`

`check_admin_token` and `drop_in_process_caches` are in
`src/admin_ops.py`, not in the route, because **importing `src.app`
constructs live Aito clients and PUTs schemas at module level.** Any test
that imports it stops being hermetic. Writing the obvious
`TestClient(app)` test made an unrelated test fail — `test_formfill_service`
asserted `4 == 6` — by disturbing its httpx mocking, and it failed
*intermittently*, depending on run order.

So the route is three lines of exception mapping and everything worth
testing is importable on its own. The cost is that no test covers the URL
or the method; the gain is a suite that does not depend on the order it
runs in.

That app-import side effect is worth fixing on its own someday. It is not
fixed here.

## Aito usage

None. This endpoint touches no Aito query; it only drops in-process state.
The one Aito-adjacent decision is *not* calling `cache.clear()`, because
that would drop a shared table.

## Acceptance criteria

- With `ADMIN_TOKEN` unset, `POST /api/cache/invalidate` is 404.
- With it set, a wrong token is 401 and the caches are untouched.
- With the right token, the response names how many entries were dropped,
  and the next read of a rebuilt precompute returns the new payload.
- `cache_entries` still exists in Aito afterwards.

## Demo impact

None on the demo path. It changes the operational sequence: promoting an
environment and rebuilding the precompute no longer needs a redeploy to
become visible.

## Out of scope

- Automatic invalidation on a database version change. That is the better
  answer and needs a version the app can cheaply poll; this endpoint is
  the thing that makes the rebuild usable today.
- Any other administrative endpoint. One route, one secret.
