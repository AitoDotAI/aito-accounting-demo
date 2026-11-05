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
checks passed on shared; the other two are in the local run below. That is
not the single 17/17 the gate asks for, and it is recorded here rather
than rounded up.

**Local run, 2026-11-05 (Antti approved the container).** A throwaway Aito
v2.11.2 container (`ghcr.io/aitohq/aito:v2.11.2-amd64`, free tier, 4 GB,
127.0.0.1:19005), removed afterwards. **Run on local v2.11.2 with demo data,
not shared master.** The free image caps a table at 10,000 rows, so the
full 128,000-invoice dataset cannot load: it holds a *slice* of 15 tenants
(CUST-0001, CUST-0100, CUST-0127..0139: 9,875 invoices, 6,176 bank lines,
557 overrides; customers and corporate_entities whole), built with the
repo's `data_loader_v2.build` into master. Numbers are therefore not
comparable to shared's. CUST-0000, the tenant `aito-check` uses, has 16,000
invoices and cannot load.

- `check_evaluate_approver_candidates_are_the_customers_own`: **pass**
  (30 cases, 1 ranked candidate, all CUST-0127's own staff; 8.7 s).
- `check_evaluate_baseline_is_scoped`: **pass, run with `CUSTOMER=CUST-0001`**
  (accuracy 0.90 vs baseline 0.37 on 30 rows; 17 s), a variant of the
  check, not the check as written. The check as written needs a database
  above the free image's 10,000-row-per-table cap (CUST-0000 has 16,000
  invoices), so it can only run as written against shared or a licensed
  engine.
- Negative control: with `scope_candidates_by` removed, the approver check
  **fails**: "the ranking offers another tenant's staff to CUST-0127:
  ['CUST-0001-EMP-0000', ...]". The check can see the leak.

The approver check, its negative control and the approver table in branch 1's
report were repeated on a second container, **v2.12.0** (shared's version since
2026-11-05 08:11), with the same slice: same results. Anything that differs
between 2.11.2 and 2.12.0 is said where it appears.

So all 17 checks have now passed somewhere: 15 on shared master, 2 on the
local slice. That is not one 17/17 run against one target.

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

1. **3 of the 255 committed `data/precomputed/*/anomalies_scan.json` files carry
   the old wording, and the guard refuses exactly those 3** (CUST-0009,
   CUST-0011, CUST-0016; a text search for "historical invoices" finds the same
   three, so they are true positives and there are no false ones). An earlier
   version of this report said "8 of 20"; that came from a sample of 20 files
   counted a different way, cannot be reproduced, and is withdrawn. These are
   the files on disk. **What Aito's `precompute_entries` table holds is a
   separate question** that only the deploy-time `./do precompute-v2` (Antti's)
   answers; until then the live demo's count of stale anomaly payloads is
   unknown.
2. Whether any (customer, vendor) pair exceeds 1000 invoices, i.e. whether
   the truncation guard is reachable in this dataset, was **not checked**;
   until it is, only the unit test covers it.
