# Verification — the evaluation surfaces rank only the tenant's own rows

Branch `fix/evaluation-approver-scope`.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/evaluation-approver-scope.md`.

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

## Offline (done)

| Check | Result |
|---|---|
| `./do test` | pass |
| `approver` sends `approver.customer_id` in the evaluate `where` | yes |
| matching `invoice_id` sends `invoice_id.customer_id` | yes |
| help `article_id` sends `article_id.customer_id` | yes |
| `gl_code`, `vendor_name`, `clicked` send no such filter | yes |
| empty `customer_id` | 400, no evaluate call |
| `predict=iban`, `domain=nope`, `predict=approver.customer_id` | refused; no evaluate call |
| `limit` 5000 / 0 / -1 | 400, no Aito call (added in this pass, e423f2b); also 400 through the running app on the local Aito |

## Live (read-only, shared v2 master)

- [x] unknown customer `CUST-9999` is a 400 with the roster loaded, and no Aito call
- [x] `aito-check`: 15 of 17 pass; the two `_evaluate` checks not run (see above)
- [x] `_evaluate` for approver, CUST-0127 and CUST-0100, limit 5 and 10, with
      and without the filter (local v2.11.2 slice, not shared master):

  | tenant | limit | filter | accuracy % | base % | meanRank | trainSamples | foreign top-1 | wall |
  |---|---|---|---|---|---|---|---|---|
  | 0127 | 5 | with | 100 | 100 | 0.0 | 9870 | 0 | 0.6 s |
  | 0127 | 5 | without | 100 | 100 | 0.0 | 9870 | 0 | 0.6 s |
  | 0127 | 10 | with | 100 | 100 | 0.0 | 9865 | 0 | 0.7 s |
  | 0127 | 10 | without | 100 | 100 | 0.0 | 9865 | 0 | 0.9 s |
  | 0100 | 5 | with | 100 | 100 | 0.0 | 9870 | 0 | 0.7 s |
  | 0100 | 5 | without | 100 | 100 | 0.0 | 9870 | 0 | 0.8 s |
  | 0100 | 10 | with | 80 | 80 | 0.2 | 9865 | 0 | 0.7 s |
  | 0100 | 10 | without | 90 | 80 | 0.1 | 9865 | 0 | 0.8 s |

  Nothing came near the 30 s stop. **The case list cannot tell the two apart**:
  the tenant's own staff win every top-1 either way, and `trainSamples` is the
  same with and without the filter (the filter shapes the candidate ranking,
  not the training set). The leak shows only in the ranking behind the case,
  which is what the aito-check asserts (see the negative control above).
  CUST-0100 at limit 10 differs by one case (80% vs 90%), a one-case sample.
- [ ] every `cases[].predicted` belongs to the tenant, ~10 tenants: **2 tenants
      only** (0 foreign in 60 cases above).
- [x] **invoice_id: measured before and after** (matching, `description,amount`,
      limit 10, local Aito 2.12.0 slice, not shared master):

  | tenant | candidates | accuracy % | meanRank | trainSamples | wall |
  |---|---|---|---|---|---|
  | 0127 | tenant's invoices | 0.0 | 33.3 | 6166 | 2.5 s |
  | 0127 | all tenants (old) | 0.0 | 7418.4 | 6166 | 4.8 s |
  | 0001 | tenant's invoices | 0.0 | 4063.5 | 6166 | 4.4 s |
  | 0001 | all tenants (old) | 0.0 | 4978.0 | 6166 | 3.9 s |

  Settles the plan's question: `trainSamples` is identical, so the linked-row
  filter does **not** drop null-`invoice_id` payments from training. Accuracy is
  0% both ways, because each invoice has one bank line and a held-out line's
  invoice has no training evidence (as perf measured, td-20261031125252403569;
  an unscoped run here took seconds, but on the full dataset it is minutes).
  **`meanRank` is what changes, and it is a number the Quality page shows:**
  that is a published-number change, Antti's to accept. It is the more honest
  number (a rank among the tenant's invoices, not among 128,000), but the
  metric itself cannot pass or fail, so no quality claim rests on it.
- [x] **article_id: scoping withdrawn from this PR (CPO review of #62).** The
      first version scoped it to the tenant exactly, which drops the 20 global
      (`customer_id = "*"`) articles from the candidates. Measured on the slice,
      CUST-0001, limit 20: exact tenant scope accuracy 5% / meanRank 2.0, no
      scope 10% / 12.5. The product's own set, `{"$or": ["*", tenant]}`
      (`help_service`), is **rejected by `_evaluate`** on both 2.11.2 and 2.12.0
      ("supports literal test/where values"). So no filter is expressible that
      is both a boundary and correct; the target stays as it was and the open
      leak (another tenant's internal article id can print in
      `cases[].predicted`) is recorded as its own item. The unit test now pins
      "not scoped" with that reason.
- [ ] tenant switch leaves no stale foreign candidate (browser)

## Findings

1. **`limit` was unbounded** on `/api/quality/evaluate` while the page said
   "capped at 300". With the unscoped cross-tenant `_evaluate` this let any
   visitor saturate shared with a URL; the only guard is a per-IP rate limit.
   Fixed here (400 outside 1..300; unknown domain/target refused before the
   cache). Behaviour change: a caller passing `limit` above 300 now gets 400.
   It takes effect only when deployed, which is Antti's.
2. **The unknown-customer guard fails open when the roster is empty**
   (`known and cid not in known`). With the roster loaded it works. Fixed
   in branch 2 as a loud report, not as fail-closed.
3. An undeclared target used to be HTTP 200 with `{"error": ...}`; now 400.
4. **`input_fields` was not allow-listed (CPO review).** It allowed the target
   as its own input (`predict=approver&input_fields=approver` reads the label),
   unknown names (an Aito error returned as 200) and unbounded cache keys.
   Now each name must be one the domain offers, the target is refused as its
   own input, and duplicates collapse. The page already hides the target from
   the checkboxes; it now also drops a stale selection before sending. Help's
   default inputs include `article_id`, so predicting `article_id` with that
   default was an existing target leak; it is now a 400 instead of a fake 100%.
5. **Cache.** Results cached before the fix would linger up to 10 minutes
   (and in the shared L2 table). The keys now carry `scoped`, so old entries are
   never read. `/api/quality/evaluations` gets the empty-customer 400 too.
