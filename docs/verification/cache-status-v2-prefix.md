# Verification — /api/cache/status reports warm when the cache is warm

**Date:** 2026-10-31 · **Branch:** `fix/cache-status-v2-prefix` · **Head:** `894b684`
**Data:** v2 environment `master` (unscoped), the environment the demo serves

**Method.** Run by the session that wrote the branch, which is a weakness and is
stated here rather than hidden: the adversary pass is meant to be someone else,
so the scenarios below are the ones its author thought of. No Playwright pass
was run — this endpoint has no UI of its own beyond one boolean in the customer
selector. What was run is the repo gate in full plus a before/after
demonstration against `origin/main`.

**No write reached the shared instance.** `src/app.py:99` calls `cache.init(aito)`
at import, which registers the persistent L2 layer on the shared DB. The
demonstration script unregisters it (`cache._aito = None`) before touching the
cache, so every `cache.set` below stayed in process memory. Writes to shared
hosts are Antti's call, and this verification did not need one.

## Verdict

The defect reproduces on `origin/main` and is fixed on this branch. The repo
gate passes in full, including all 16 live Aito checks. One limitation is noted
at the end.

## Acceptance criteria

| Criterion | Result |
|---|---|
| In v2 mode, a tenant whose pages are cached reports `*_warm: true` | ✅ all five flags true on this branch after warming all five keys (`CUST-0100`, `_V2 = "v2:"`) |
| The same script on `origin/main` misreports | ✅ 5 of 5 report cold while warm — the defect, demonstrated rather than argued |
| A tenant with nothing cached reports `false` on all five | ✅ `tests/test_cache_status_reports_the_right_keys.py::test_a_cold_cache_reports_cold`, parametrised over all five surfaces |
| All page-cache call sites go through `page_cache_key` | ✅ 15 sites replaced; 10 were already prefixed, 5 were the bug |
| No hand-spelled page cache key remains in `src/app.py` | ✅ `grep -n 'f"\(invoices\|quality\|matching\|rules\|anomalies\):' src/app.py` returns nothing, and a test asserts it |
| v1 mode unchanged | ✅ `_V2` is `""` there, so the old spelling was already correct; the builder returns the same string |
| `./do test` | ✅ 250 passed |
| `./do check` (test + fmt + live aito-check) | ✅ 16/16 checks passed on v2 env `master` |
| No client gets a worse answer | ✅ the only consumer is `CustomerSelector.tsx:37`, which polls this endpoint every 5 s and showed "not warm" permanently in v2 mode; it now shows the truth |

## Scenarios tried to break it

- **Reverted the fix inside the builder** (prefix dropped, the original bug):
  6 of the 12 new tests go red. Recorded because the *first* version of those
  tests did **not** catch it — see below.
- **Ran the demonstration on `origin/main`** rather than trusting a unit test to
  describe the old behaviour. All five flags stayed false with all five keys
  warm, which is the user-visible defect.
- **Checked v1 mode**, where `_V2` is empty: the pre-fix spelling was already
  correct there, so this is a v2-only defect and the fix is a no-op on v1.
- **Looked for other key families** that could have the same split. `mined_rules`,
  `formfill`, `formfill_templates`, `matching_ctx` and `matching_why` all carry
  `_V2` consistently on both sides and are deliberately left alone: folding them
  into the builder would mean a builder taking arbitrary suffixes.

## Failure found in the verification itself

The first version of `tests/test_cache_status_reports_the_right_keys.py` passed
with the bug reinstated, for two reasons worth recording because both are easy
to repeat:

1. It computed its expected key by calling `page_cache_key` — the function under
   test. An expectation built that way agrees with the code however wrong the
   code is.
2. The suite runs with `AITO_V2_ENV` unset, so `_V2` is `""`, and the buggy and
   correct builders return identical strings. **The bug only exists in v2 mode,
   so the test has to be in v2 mode.**

Fixed by spelling the keys as literals and setting `_V2` in an autouse fixture.
A twelfth test greps the module for hand-spelled page keys, so the next copy of
this bug cannot be added quietly.

## Known limitation, not fixed

The verification exercises the in-process cache only. The persistent L2 layer
uses the same key through the same builder, so the defect is covered
structurally, but no part of this pass proves an L2 round trip agrees — that
would need a write to the shared instance. If someone wants that covered, it
belongs in a run where a shared write is approved.

Also: this branch carries a second commit that makes `src.app` importable
without calling Aito (`AITO_SKIP_STARTUP_WARMUP`) and unsets `PYTHONPATH` in
`./do test`. The first is what makes any test of this endpoint possible on this
host; the second is why the suite can collect at all once a test imports
pydantic. Both default to the previous behaviour for a running server.
