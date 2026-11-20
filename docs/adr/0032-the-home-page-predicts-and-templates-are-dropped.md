# 0032. The home page predicts per tenant, with its evidence; vendor templates are dropped

**Date:** 2026-11-20
**Status:** proposed

## Context

Form Fill and the home page showed a "template" for a vendor: the most
common GL account, approver and cost centre among the vendor's last 50
invoices. It was computed with `_search` and a Python `Counter`. Nothing in
it was predicted: its "confidence" was a ratio of counted rows, not a
probability, and it carried no `$why`. On the home page, whose point is
"same vendor, different tenants, different predictions", the answer was a
frequency table. Next to Form Fill's real `_predict` fields it also read as
the same kind of output when it was not.

## Decision

- Each tenant card on the home page shows Aito's `_predict` for that tenant
  and vendor: GL account, approver and cost centre, each with its
  probability. The GL account carries its `$why`, behind the same `?` popup
  Invoice Processing uses.
- Form Fill drops the quick-start cards and the "Template match / Apply
  template" banner. The form still opens on a worked example (the first
  vendor in the tenant's list), and every other field is predicted.
- `predict_template`, `/api/formfill/template` and `/api/formfill/templates`
  are removed.

## Aito usage

Three `_predict` calls per tenant and vendor (`gl_code`, `approver`,
`cost_centre`), the same call Form Fill makes, with `customer_id` as
evidence and the approver candidates limited to the tenant's staff
(`approver.customer_id`). Below Aito's noise floor (`$p` <= 0.10) the GL
account gets no answer: the tenant has too little history with the vendor.

## Acceptance criteria

- A user can pick a shared vendor and see, per tenant, the predicted GL
  account with its probability.
- A user can open `?` on a tenant's GL account and see the `$why` chain.
- A tenant with too little history for the vendor says so, and shows no
  guessed account.
- Form Fill has no template cards and no Apply template button.

## Demo impact

`docs/demo-script.md` step 3 no longer starts from quick-start cards.

## Out of scope

- Prediction semantics and thresholds are unchanged (the noise floor is the
  existing Form Fill one).
- A precomputed `landing.json` in the old shape is recomputed live until
  `./do precompute-v2` rewrites it. That run is a deploy step and is not part
  of this change.
