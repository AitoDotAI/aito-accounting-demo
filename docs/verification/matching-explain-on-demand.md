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

So all 17 checks have now passed somewhere: 15 on shared master, 2 on the
local slice. That is not one 17/17 run against one target.

**Not done:** browser/Playwright steps (screenshots, devtools network).
Rows that need them are left unticked.

## Results

| Criterion | Result |
|---|---|
| ranking `_predict` selects no `$why` | **yes, live**: `check_payment_matching_ranks` "6 factors fetched for one row, none in the list" |
| `/api/matching/explain` requires `invoice_id` | yes (FastAPI `Query(...)`) |
| explain for a cached other invoice -> 409, entry evicted | yes (tests) |
| ranking and explanation share `where` and limit | covered by tests; live body comparison not done |
| app on the local Aito, CUST-0127 (8 pairs, 6 Aito-matched) | the list carries `explanation: []` on every row; `GET /api/matching/explain` with the right invoice -> 200 (14 s cold: it rebuilds the contexts); with another invoice -> **409**, and the next correct call rebuilds -> 200 (1.2 s); other tenant's `customer_id` with this `transaction_id` -> 404; no `invoice_id` -> 422 |
| `cache_entries` on the local Aito after those calls | only `matching:v2:<tenant>` keys; no `matching_ctx` or `matching_why` row (contexts stayed local) |
| a reference-matched row has no context -> 404 | yes (tests) |
| other tenant's `transaction_id` -> 404, never another tenant's explanation | yes: contexts and explanations are keyed by customer |
| `./do test` | pass |
| browser: skeleton, retry link, drift message, prefetch order, tenant switch | **not done** |

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

## Not covered

The drift case (`matching_pairs.json` edited so a row names another
invoice) was not forced in a browser; the endpoint's 409 path is covered by
unit tests only.
