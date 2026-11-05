# Verification — the stack as it landed on main

Main at `8b9af63` (#62 approver scope, #64 book and roster, #65 matching explain,
#66 stale precompute, #67 latency findings, #68 anomaly counts, #69 cache keys,
#70 explain served-page-first, #71 L2 counts, #72 pairing lock). **#63 (the
`invoice_id` candidate scope, a shown-number change) is not merged** and is not
part of what is verified here. Written 2026-11-05 by the session that did the
per-branch adversary passes (`docs/verification/<branch>.md`); this one looks at
the branches *together*.

## What was run

| Check | Result |
|---|---|
| `tests/` on main (dummy Aito) | 427 pass |
| `./do book` replay (real URL for snapshot keys, no network) | 30/30 |
| `scripts/baseline_collisions.py` over the 31 baselines | no shared measurements |
| `scripts/prove_book_assertions.py` | all 24 assertions fail when broken |
| `scripts/find_unfalsifiable_tests.py tests` | 4 assertion-free tests: the 2 the CPO already annotated, and 2 added by this stack (`test_the_largest_limit_the_page_offers_is_accepted`, `test_the_inputs_the_page_offers_are_accepted`), now given an explicit `is None` assertion in the PR that carries this report |
| `aito-check`, the 15 checks that do not use `_evaluate`, read-only against shared master (v2.12.0), one at a time | 15/15 pass |
| the 2 `_evaluate` checks | **not run on shared** (standing rule); passed on a local v2.11.2 and v2.12.0 slice earlier, the baseline one as a `CUST-0001` variant |
| `./do check` as a whole | not run (it includes the `_evaluate` checks) |
| browser steps for every branch | **not done** (frontend build failed once, not retried) |

## Cross-feature scenarios

1. **Stale precompute -> live page -> badge -> explain, one tenant** (TestClient,
   fake matcher). A matching payload without `matched_by_aito` is refused (#66),
   the page falls through to the live pairing under the lock (#72, one
   `match_all` call), the explain endpoint answers 200 for the shown invoice and
   409 for the stale payload's invoice (#65, #70), a second page load is served
   from the cache (no second pairing). Evaluate with the target as its own input
   and `/api/quality/evaluations` for an unknown customer are both 400 (#62, #64).
2. **Key prefix under each API generation.** With `AITO_V2_ENV` unset, `master`
   and `v2-demo`, `page_cache_key`/`derived_key` produce unprefixed, `v2:` and
   `v2:` keys; `/api/help/stats` now carries the prefix (found by #69's guard).
3. **Aito unreachable, live app** (dummy URL). `/healthz` starts at 0 failed L2
   operations and shows 1 write, 1 delete and 8 reads after one page load, with
   `last_error` of type, status and path only and the detail on stderr (#71).
4. **Precompute written by the reworked writer is served** (local v2.12.0, earlier
   in this pass): inline explanations pass #66's staleness guard, the page loads
   in 87 ms and an explain in 19 ms (#65 + #66).

## Findings

1. **Aito unreachable -> a cached empty matching page** (pre-existing; ticket
   td-20261105161953190031). `match_all` swallows `AitoError` into
   `{"pairs": [], "metrics": {"total": 0}}`, which `_match_and_cache` caches for
   300 s in L1 and the shared L2. It also means #72's failure sharing never sees
   an Aito failure, only other exceptions. Left alone: turning the empty 200 into
   a 503 is Antti's call.
2. **`cache.init` counted nothing when L2 was down from the start** (found here;
   fixed in the PR carrying this report). A 4xx still means "table exists".
3. **Two of this stack's own tests asserted nothing** (found here; fixed).
4. `badge_metrics` still returns `{}` -> badge 0 for a cached payload with no
   `metrics` key (known since #66's report; not reachable from the shapes the app
   writes).
5. The artefact in the first test run on this pass (two failures) was this
   session's `rsync` of an older `data/` over the worktree's tracked
   `data/precompute_predictions.py`, not a defect in main; recorded because it
   looked like one for five minutes.

## What this does not establish

- Nothing is deployed. Merge is not deploy: the evaluate `limit` cap and its new
  400s, the evaluate `input_fields` allow-list, the roster reporting, explain on
  demand and the staleness guard take effect when Antti deploys, and the deploy
  needs `./do precompute-v2` paired with it.
- What Aito's `precompute_entries` table holds (stale or current) is only answered
  by that deploy-time run.
- No browser step ran on any branch.
- #63 changes `meanRank` for the Linked-invoice evaluation (CUST-0127 7418 -> 33)
  and waits for Antti.
