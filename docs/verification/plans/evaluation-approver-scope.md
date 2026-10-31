# Plan — the evaluation surfaces rank only the tenant's own rows

Branch `fix/evaluation-approver-scope` · head `23a1c80` · **plan, not a report**

Tickets td-20261030202058894219 (approver) and the remainder of
td-20260901082623647538 (PR #58 fixed Form Fill only).

## What the branch claims

| Criterion | Result |
|---|---|
| `/quality/predictions` with predict=approver sends `approver.customer_id` in the evaluate `where` | |
| The Quality matrix's approver task sends it too | |
| Payment matching's `invoice_id` target sends `invoice_id.customer_id` | |
| Help's `article_id` target sends `article_id.customer_id` | |
| Unscoped targets in those domains (`vendor_name`, `clicked`, `gl_code`) send no such filter | |
| A scoped target without a customer_id is a 400, not an unscoped query | |
| Every `cases[].predicted` on screen is a row belonging to the selected tenant | |
| The filter costs no accuracy at 200 samples (the claim in commit `1bb1b7f`) | |

## Steps

```bash
./do test                                    # 248 pass
./do aito-check --v2                         # includes the two candidate-scope checks
```

Then, per domain, in the browser at `/quality/predictions`:

1. Pick a tenant with few staff — `CUST-0127` has 1, `CUST-0100` has 2.
   A single-employee tenant is the sharpest case: every candidate beyond
   rank 1 must be absent, not merely lower.
2. Run the approver evaluation. Capture the `_evaluate` request body.
3. Repeat for Payment Matching → *Linked invoice*, and Help → *Article id*.
4. Repeat one unscoped target (GL code) to confirm it carries no filter.

## What to capture

- The `_evaluate` body for each of the five targets above: the `where`
  block is the evidence, and `trainSamples` / `testSamples` are what the
  open question below turns on.
- Screenshot of the per-case table for the single-employee tenant, wide
  enough to read `predicted` on every row.
- `X-Aito-Ms` and `X-Aito-Ops` for each run, scoped and (by reverting
  the config entry locally) unscoped, if you want to re-check the cost
  claim at 200 samples.

## Tried to break it

- Request `predict=approver` with `customer_id=` empty, and with a
  customer that does not exist. Expect 400 both times, and **no**
  `_evaluate` in `X-Aito-Calls`.
- Request `predict=iban` — a target nobody declared. Expect an error and
  no Aito call: a target with no declaration cannot be scoped, so it
  must not be sent.
- Switch tenants with the evaluation still rendered, and confirm no
  stale foreign candidate survives the switch.
- Hunt for a foreign id in the per-case table across ~10 tenants. The
  probe in the commit message found the tenant's own employee at rank 1
  in all ten tenants tried, so nothing foreign has been *seen*; the
  claim is about the candidate set, not about rank 1.

## Open question — must be settled here

`bank_transactions.invoice_id` is nullable (`src/data_loader.py:118`).
`invoice_id.customer_id = <tenant>` is a condition on the linked row, so
a payment with no invoice has no linked row to satisfy it and is
presumably dropped from training — while `testSource` is built from
`{"customer_id": ...}` on the table and still includes it.

1. Compare `trainSamples` for `invoice_id` with and without the filter.
2. Compare accuracy and `meanRank`.
3. If accuracy falls, decide whether `testSource` should gain
   `"invoice_id": {"$exists": true}` so the test set and the candidate
   domain agree.

Record the decision either way. A worse number for a better question is
defensible; a surprise in a demo is not. `approver` is non-nullable
(`data_loader.py:88`) and is unaffected.
