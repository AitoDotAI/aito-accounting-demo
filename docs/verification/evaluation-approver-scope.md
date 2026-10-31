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
checks passed; that is not the 16/16 the gate asks for, and it is
recorded here rather than rounded up.

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
| `limit` 5000 / 0 / -1 | 400, no Aito call (added in this pass, e423f2b) |

## Live (read-only, shared v2 master)

- [x] unknown customer `CUST-9999` is a 400 with the roster loaded, and no Aito call
- [x] `aito-check`: 15 of 17 pass; the two `_evaluate` checks not run (see above)
- [ ] `_evaluate` body per target for CUST-0127 / CUST-0100 (needs `_evaluate`)
- [ ] every `cases[].predicted` belongs to the tenant, ~10 tenants (needs `_evaluate`)
- [ ] **invoice_id training scope** (the plan's open question): `trainSamples`,
      accuracy, `meanRank` with vs without the filter. **Not measured.** The
      unscoped `_evaluate` at limit 200 saturated shared; the measurement
      moves to a local Aito, pending Antti's yes. Until then the question
      stays open: a payment with no invoice has no linked row to satisfy
      `invoice_id.customer_id`, so it is presumably dropped from training
      while `testSource` still includes it.
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
