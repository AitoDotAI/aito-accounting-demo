# Verification — a count is quoted only when it is complete

Branch `fix/anomaly-explanation-counts`.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/anomaly-explanation-counts.md`.

**Environment.** Offline checks used a dummy Aito URL with the app's L2
cache unregistered, so nothing could be written to shared. Live checks
were read-only `_search`/`_predict`/`_relate` calls against shared v2
`master`, one at a time with gaps. **No `_evaluate` was sent to shared**
at the CPO's instruction, after `_evaluate` calls saturated it that
morning (429, inFlightWeight 30 of 32, then out of memory). The two
`aito-check` checks that use `_evaluate` were therefore not run:
`check_evaluate_baseline_is_scoped` and
`check_evaluate_approver_candidates_are_the_customers_own`. 15 of 17 live
checks passed; that is not the 16/16 the gate asks for, and it is
recorded here rather than rounded up.

**Not done:** browser/Playwright steps (screenshots, devtools network).
Rows that need them are left unticked.

## Results

| Criterion | Result |
|---|---|
| flag text states "N of M" only from a counted M | yes (tests) |
| a truncated sample is not quoted as a count | yes (unit test only) |
| a failed count query does not read as an empty history | yes (tests) |
| stale `anomalies_scan` wording is refused by the precompute guard | yes (tests) |
| `scripts/find_unfalsifiable_tests.py` | reports 2 assertion-free tests: `test_admin_ops.py:46`, `test_cache_versions.py:165`; the CPO records both as already mutation-checked and annotated |
| `./do test` | pass |
| one screenshot per sentence form, `_search` body behind each | **not done** |

## Findings

1. **8 of 20 locally precomputed `anomalies_scan.json` files still carry the
   old "N of N historical invoices" wording.** The staleness guard in this
   branch is what keeps them from being served; they need `./do precompute-v2`
   (Antti's) to be rebuilt.
2. Whether any (customer, vendor) pair exceeds 1000 invoices, i.e. whether
   the truncation guard is reachable in this dataset, was **not checked**;
   until it is, only the unit test covers it.
