# Verification — the evaluation surfaces rank only the tenant's own rows

Branch `fix/evaluation-approver-scope` (rebased onto main at 33d5074) ·
plan: `docs/verification/plans/evaluation-approver-scope.md` ·
verified by a session that did not write the branch.

**Status: DRAFT — offline half done, live half not yet run.** Shared Aito
answered every `_evaluate` with `429 server overloaded
(inFlightWeight 30, capacity 32)` at ~11:30 Helsinki on 2026-10-31; probing
stopped at the CPO's request. Unticked rows below need the live pass.

## Offline (done)

Environment: `AITO_API_URL=http://127.0.0.1:9 AITO_API_KEY=dummy`, so no
call can leave the machine; the app's L2 cache layer unregistered
(`cache._aito = None`), so no row is written to shared.

| Check | Result |
|---|---|
| `./do test` | 260 passed |
| `approver` sends `approver.customer_id` in the evaluate `where` | yes |
| Payment matching `invoice_id` sends `invoice_id.customer_id` | yes |
| Help `article_id` sends `article_id.customer_id` | yes |
| `gl_code`, `vendor_name`, `clicked` send no such filter | yes |
| `customer_id=` empty | 400, 0 evaluate calls |
| `predict=iban`, `domain=nope` (undeclared) | 0 evaluate calls; see finding 2 |
| `predict=approver.customer_id` (a spelled-out filter key as target) | 0 evaluate calls |
| Injection-shaped `customer_id` | passed through as a value, never as a key; see finding 1 |

## Live (to do)

- [ ] `./do check` incl. `aito-check` (16/16 expected)
- [ ] unknown customer `CUST-9999` is a 400 and no `_evaluate` (see finding 1)
- [ ] `_evaluate` body per target for `CUST-0127` (1 staff) and `CUST-0100` (2)
- [ ] every `cases[].predicted` belongs to the selected tenant, ~10 tenants
- [ ] **invoice_id training scope** (the open question): `trainSamples`,
      accuracy, `meanRank` with vs without the filter; same for `article_id`
- [ ] tenant switch leaves no stale foreign candidate (browser)

## Findings

1. **The unknown-customer guard fails open when the roster is empty.**
   `validate_customer_middleware` checks `known and cid not in known`; with
   an empty roster every id passes. Offline, `CUST-9999` reached `_evaluate`
   with the scoped filter. Pre-existing, not introduced by this branch; the
   live run says whether the roster is ever empty in production.
2. **An undeclared target is HTTP 200 with `{"error": ...}`**, not a 4xx.
   No Aito call is made, which is the plan's requirement, but a client that
   checks status codes sees success. Pre-existing convention in this endpoint.
3. The new `if not customer_id` 400 in `quality_evaluate` is unreachable
   through HTTP, because the middleware already answers 400 first. It is
   harmless defence for direct callers of the function.
