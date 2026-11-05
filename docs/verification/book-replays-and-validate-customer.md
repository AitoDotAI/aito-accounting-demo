# Verification — the book replays, and its assertions can fail

Branch `fix/book-replays-and-validate-customer`.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/book-replays.md`.

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
| `./do book` replays 30/30, twice, no "cannot replay" | yes (real Aito URL in env so snapshots key; replay makes no request) |
| `./do prove-assertions` | **All 24 assertions fail when broken** (22 on the author's branch) |
| `book-accept` refuses two entities sharing one measurement | yes: identical support pairs (also written `7383 / 16000`) and identical lifts are refused |
| a lift written 2.3 vs 2.30 | **was missed; fixed** in this pass (lifts compared as numbers) |
| `--i-know` overrides and says so | read in `do`, not run |
| bad `customer_id` is still 400 after `validate_customer()` was removed | yes: empty, `NOPE` on `/api/invoices/pending` and `/api/matching/pairs` |
| `./do test` | pass |
| app on the local Aito, roster loaded | `/healthz` `{ok: true, roster_count: 255}`; `/api/health` status `ok`; `NOPE` -> 400 |

## Findings fixed in this pass

1. **Collision guard compared lifts as text**, so a dropped condition slipped
   through when two rows were formatted to different precision.
2. **`book/test_03` had plain `assert`s inside loops**, which `prove-assertions`
   cannot see and which pass if the loop never runs. Converted to `assertln`.
   That exposed a fourth, truly unreachable assertion: the v1 `fs` branch
   (`f_on <= f`), since v2's `$patterns` returns no `fs`. The dead branch is
   removed.
3. **An empty customer roster was invisible.** `data/customers.json` is
   generated and gitignored; the Dockerfile copies `data/` from the build
   context, so an image built from a clean checkout has no roster and
   `except Exception: set()` turned validation off silently. Now reported:
   stderr "customer_id validation is OFF", `roster_count` on `/health`,
   status `degraded` on `/api/health`. **No answer changes.** Failing closed
   would 400 every `/api` call on such an image; that needs a build-time
   check that the image contains the roster, and is Antti's call.

## For a human glance: re-captured baselines (author's commit 651c0dc)

- `test_relate_category_to_gl`: telecom now "no data"; supplies/facilities/
  software/consulting supports and one GL (software 6100 -> 1600) changed.
- `test_relate_vendor_to_gl`: the old baseline listed four vendors with the
  identical `7383/16000 lift=2.3` (a dropped condition); replaced by
  per-vendor numbers (e.g. Avarn 1300/1328 lift 10.3).
- `test_predict_invoice_from_bank_txn`: probabilities moved a lot (e.g.
  0.0000 -> 0.9744 for Avarn; one wrong vendor became the right one).
- `test_mine_rules_for_customer`: 2 rules -> 8.
- `test_predict_template_for_recurring_vendor`: GL label now Finnish
  ("Aineet ja tarvikkeet").
- `test_help_evaluate_on_unseen_customer`: prints "cold start is allowed:
  ranking falls back to global" (global fallback is exactly what ADR 0030
  questions).
- `test_relate_latency`: lifts 21.94 -> 4.97 / 3.30 and rule counts changed.

## Findings left open

- Two `lift=` tokens with different decimals but not equal are, correctly,
  not collisions; support pairs under denominator 10 are skipped by design.
