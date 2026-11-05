# Verification — only the expanded row asks why, and it asks about itself

Branch `fix/matching-explain-on-demand`.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/matching-explain-on-demand.md`.

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

## Design after the CPO review of #65 (2026-11-05)

On demand is for the **live** page only. A precompute is built once and served
for days, so it keeps its explanations: `precompute_matching` passes
`inline_explanations=True`, the ranking asks `$why` for those pairs, and every
Aito-matched row carries its own explanation. Before this rework, regenerating
the precompute would have dropped them, and every page load would then have
rebuilt contexts (14 s cold) and fetched `$why` for every row. The background
prefetch is gone: only the expanded row asks, including the auto-opened first
row.

## Results

| Criterion | Result |
|---|---|
| ranking `_predict` selects no `$why` (live page) | **yes, live**: `check_payment_matching_ranks` "6 factors fetched for one row, none in the list" |
| the precompute path asks `$why` and ships each Aito-matched pair's explanation | yes (tests; the script passes `inline_explanations=True`; mutating it off fails) |
| `/api/matching/explain` requires `invoice_id` | yes (FastAPI `Query(...)`) |
| a page that already carries the explanation is answered from the page, no Aito | yes (tests) |
| an `invoice_id` the served page does not show -> **409, no recompute, no eviction** | yes (tests; evicting or recomputing again fails them) |
| a payment the served page does not have, or one matched by reference -> 404, no recompute | yes (tests) |
| a recorded substitute that Aito now ranks directly is refused, not explained | yes (test; the guard set to `False` now fails it, it did not before) |
| ranking and explanation share `where` and limit | covered by tests; live body comparison not done |
| **re-run live on a local Aito v2.12.0 with the reworked code** (slice, CUST-0127: 8 pairs, 6 Aito-matched; 2026-11-05) | live page: the list ships `explanation: []` on every row (4.7 s cold); right invoice 200 in 0.8-1.3 s (contexts present), cached 5 ms; a bogus invoice 409 in 6-25 ms with nothing recomputed; the reference-matched row and an unknown payment 404 in 20-35 ms. **Precompute page** (`precompute_matching` run against the local Aito and stored): all 6 Aito rows carry 8 factors inline, the page loads in 87 ms, an explain is answered from the page in 19 ms, a bogus invoice 409 in 14 ms, an unknown payment 404. Not re-run: a live page whose contexts were lost (restart), which is unchanged code |
| other tenant's `transaction_id` -> 404, never another tenant's explanation | yes: contexts and explanations are keyed by customer |
| `./do test` | pass |
| browser: skeleton, retry link, drift message, tenant switch | **not done** |

## What reaches the shared L2 table

- The pairs page (`matching:v2:<tenant>`): yes, as before.
- The explain **contexts** (`matching_ctx`): no, `local_only=True`.
- The **explanation payloads** (`matching_why:...:<transaction_id>`):
  **yes.** `cache.set(explain_key, ...)` has no `local_only`, so each one is
  written to the shared table, a few KiB each. Re-run on a local v2.12.0:
  `cache_entries` held `matching:v2:CUST-0127` and two `matching_why:...` rows.
  **Why the earlier listing showed no `matching_why` row:** it was not a
  failed write. In the earlier (old-design) run I asked for the right invoice
  (200, written), then for a wrong one, which in that design evicted the row it
  had just cached (`cache.delete`, L1 and L2), and listed afterwards. The
  rework no longer evicts. L2 writes are still best-effort by design
  (`cache.set` swallows `AitoError`/`TypeError`), so a write that fails
  is silent; the local run shows the success path only.

## Findings fixed in this pass

1. **Explain contexts went to the shared L2 table.** Each holds the whole
   open ledger as of that payment; built offline from the real shape they
   are 27-43 KiB per tenant against a 7 KiB pairs payload, written for every
   tenant the keep-warm pass visits. That undoes the byte saving the branch
   exists for. They are now `cache.set(..., local_only=True)`; a lost
   context costs one rebuild.
2. **Concurrent cold explains each ran the whole pairing** (test: 4 threads,
   4 rebuilds). They now share one under `cache.compute_lock`.
3. The matching keys now go through `page_cache_key` (#59's guard failed on
   this branch's hand-spelled `matching:` keys after rebase, which is the
   guard working).
4. **(CPO review) A regenerated precompute dropped the inline explanations**
   and the background prefetch fetched `$why` for every row. Fixed as above.
5. **(CPO review) A bogus `invoice_id` evicted the real row's cached
   explanation and could force a 14 s recompute.** Now answered 409 from the
   served page, with nothing evicted or recomputed.
6. **(CPO review) The substitute-now-ranked guard had no test.**

## Not covered

A drifted ledger on a **live** page whose contexts were lost (restart, another
instance) still ends in a 409 for that row until the page is reloaded; the page
says so, and it no longer touches precomputed pages. The drift case was not
forced in a browser.
