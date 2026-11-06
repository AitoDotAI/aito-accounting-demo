# Verification — a precompute missing the fields its page reads is refused

Branch `fix/precompute-refuses-stale`.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/precompute-refuses-stale.md`.

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

**Browser steps: done 2026-11-06**, see `docs/verification/browser-pass.md` (local v2.12.0, screenshots committed).
Rows that needed them are updated below where the pass covered them.

## Results

| Criterion | Result |
|---|---|
| `matching_pairs` without `metrics.matched_by_aito` refused | yes (tests) |
| pairs with none carrying `matched_by` refused | yes (tests) |
| refusal prints once per (customer, payload) | yes (tests) |
| names `./do precompute-v2` | yes |
| `pairs: []` with correct metrics is served | yes: `test_a_genuinely_empty_ledger_with_the_current_metrics_is_served` (added in the CPO review; refusing every empty ledger now fails it. The report said "tests" before that test existed) |
| the writer's own empty payload (`EMPTY_MATCHING`, written by `--lite-threshold`) is served | **was refused; fixed** (CPO review): it lacked `matched_by_aito`/`matched_by_reference`, so every lite tenant was refused on every request; test added |
| a name with no check (`invoices_pending`) passes untouched | yes (tests) |
| nav badge is `null` when its payload is refused/absent, never 0 | yes (tests) |
| browser: page and badge agree before/after editing a precompute | **done**, browser-pass row 6: the refused payload's numbers are not shown, the page is live, the badge API agrees (screenshot 06) |

## Not in this PR

The plan's `anomalies_scan` criterion (a payload whose flag text states a
probability as a row count is refused) is **carried by stack 6**
(`fix/anomaly-explanation-counts`, #68), whose report records the staleness
check for that wording. It is not tested here.

## Findings

1. **A second spelling of the page cache key.** `src/badges.py` builds
   `f"{cache_prefix}:{v2_prefix}{customer_id}"` itself, outside the
   guard #59 added (which reads only `src/app.py`). Each is correct alone;
   together a change to the prefix convention would drift the badge path
   silently, which is the bug #59 fixed. **Left for a follow-up PR**: red first by planting a hand-spelled key in
   a second file, then have the guard scan all of `src/`. Done in #69, which
   also tests the badges under `v2:`.
2. A matching payload where only *some* pairs carry `matched_by` is served
   (the check is `any`). Mixed payloads are not a known production shape.
3. `badge_metrics` returns `{}` (not `None`) for a payload that has no
   `metrics` key, so such a cached payload yields badge 0 beside a page
   that may show data. Not reachable from the shapes the app writes today.

## Follow-ups from the CPO review (not blocking)

- The v2 key prefix was untested (tests run with `_V2 = ""`); #69 tests the
  badges under `v2:`.
- `/api/matching/pairs` has no compute lock on the live path: a refused tenant
  cold-starts `match_all` concurrently per visitor on shared. Not done.
- `/api/matching/explain` checks the cached explanation before the served page,
  so a stale L2 explanation can 409 for up to an hour after a rebuild. Not done.
- Deploying this stack needs `./do precompute-v2` paired with it (Antti's):
  until the committed precomputes are rebuilt every tenant falls through to the
  live path.
