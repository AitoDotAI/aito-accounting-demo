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
checks passed; that is not the 16/16 the gate asks for, and it is
recorded here rather than rounded up.

**Not done:** browser/Playwright steps (screenshots, devtools network).
Rows that need them are left unticked.

## Results

| Criterion | Result |
|---|---|
| ranking `_predict` selects no `$why` | **yes, live**: `check_payment_matching_ranks` "6 factors fetched for one row, none in the list" |
| `/api/matching/explain` requires `invoice_id` | yes (FastAPI `Query(...)`) |
| explain for a cached other invoice -> 409, entry evicted | yes (tests) |
| ranking and explanation share `where` and limit | covered by tests; live body comparison not done |
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
