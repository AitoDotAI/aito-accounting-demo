# 0018. Payment matching: fix the direction, the ledger, and the explanations

**Date:** 2026-09-04
**Status:** accepted

## Context

Payment Matching broke during a live demo. The predictions were fine; the
explanation panel was not. One expanded match showed:

```
BASE PROBABILITY   Historical rate for CUST-0000-INV-000136        0%
COUNTER-EVIDENCE   When description is ARKKITEHTIRYHMÄ REINO
                   KOIVULA OY - 07042026 Viite: 3886111
                   and amount is 7807.0                          × 0.7×
                            0% × 0.7 = 58%
```

Three things are wrong at once. The base rate names `INV-000136` while
the row matched `INV-000004`. The payment's own description — the reason
for the match — is labelled *counter-evidence*. And the arithmetic is
impossible.

Aito was not at fault. Every hit's `$why` correctly describes that hit,
verified against the live v1 instance: for each of the five candidates,
the `baseP` proposition names the same `invoice_id` as the hit carrying
it. All four defects are ours.

Alongside them, the view had a data-shape problem. It fetched 10 bank
transactions and 20 *unrelated* invoices, matched what it could, then
listed every leftover invoice as "unmatched". So the header read
**"5 matched · 15 unmatched", a 25% match rate, for a matcher that was
working** — those 15 invoices were never any fetched payment's target.

## Decision

### 1. An explanation must describe the invoice it appears under

`match_bank_txn_to_invoice` has two paths. A *direct* match pairs the
invoice Aito ranked. An *indirect* match substitutes a different invoice
from the same vendor whose amount fits better — and used to carry over
Aito's `$why` from the invoice Aito ranked. That is how `INV-000136`'s
explanation ended up under `INV-000004`.

The substituted match now discards that `$why` and states what actually
decided it: same vendor, better amount fit, naming the invoice Aito
ranked. It reads as a different *kind* of match, which it is.

This also explains the "counter-evidence" label: a lift of 0.7 is
genuinely counter-evidence *for `INV-000136`* — that payment is not its
payment. Correct explanation, wrong invoice.

### 2. Stop rounding a link-target base rate to zero

`_extract_why_factors` rounded `base_p` to four decimals. A GL code's
base rate (~0.46) survives that; predicting a link target such as
`invoice_id` has a base rate near `1/128000 = 7.8e-06`, which becomes
exactly `0.0`. The factor chain then starts from a literal zero.

Base rates now keep four *significant figures*, and the UI renders
anything below 0.01% as `<0.01%` rather than `0%`.

### 3. Show arithmetic that is true

`WhyCards` renders `base × lift₁ × lift₂ … = confidence`. On Invoice
Processing that is honest, because `confidence` **is** `$p` — the
product of the chain. Payment matching blends Aito's probability with an
amount-proximity score (`aito_p × 0.4 + amt_score × 0.6`), so its
confidence is not reachable by multiplying those factors, and the `=`
asserted something false.

The footer now shows the chain's own product, and an optional
`blendNote` explains the extra step and the final number. An equation on
screen should be checkable by eye.

### 4. Match payments to invoices, not invoices to payments

A payment arrives and must be assigned to an invoice. An invoice with no
payment is unpaid — not a failure. The view now says so:

- **The ledger contains the payments' invoices.** People do not pay
  invoices that are not in the ledger. `match_all` fetches the payments,
  then builds the open-invoice pool from the invoices those payments
  settle *plus* decoys, so choosing correctly is a real discrimination
  rather than a lookup in a pool that cannot contain the answer.
- **Only a payment can be unmatched.** Leftover invoices are no longer
  padded into the result as failures.
- **The table reads left-to-right in the direction of the decision** —
  incoming payment, then assigned invoice. It previously listed invoices
  first, which read as invoice → payment.

Building the ledger uses `bank_transactions.invoice_id`, the fixture's
ground-truth link, *only* to decide which invoices are outstanding; a
real deployment reads that from its AP system. The matcher never sees
it — it gets `description` and `amount`, and re-derives the pairing.

### 5. Measure it

Every other predictive view can state its accuracy. Matching could not:
the UI's "match rate" counts pairs produced, not pairs that are *right*,
so a matcher that assigned every payment to the wrong invoice would
score 100%.

`./do eval-matching` scores the matcher against
`bank_transactions.invoice_id` and reports accuracy, coverage, precision
on asserted matches, and the failing cases.

## Aito usage

Unchanged: `_predict` on `bank_transactions.invoice_id`, which traverses
the schema link and returns invoice rows ranked by association with the
payment's `description` and `amount`, with `$why` + `highlight`. See
`docs/aito-cheatsheet.md`. No new query shapes.

Confirmed against the live v1 instance while diagnosing: each hit's
`$why` `baseP` proposition names that hit's own `invoice_id`.

## Acceptance criteria

- When a match is expanded, the base probability names **the invoice in
  that row**.
- When a match came from a same-vendor substitution, the panel says so
  and names the invoice Aito ranked, instead of showing that invoice's
  factors.
- A base rate below 0.01% renders as `<0.01%`, never `0%`.
- The equation shown equals the product of the factors above it; where
  the final confidence comes from a blend, that step is stated
  separately.
- The matching table's first column is the incoming payment.
- Only payments appear as `unmatched`.
- `./do eval-matching` reports accuracy against ground truth.

## Demo impact

`docs/demo-script.md` step 4 changes: the view is read left-to-right as
payment → invoice, and the headline number is no longer diluted by
unpaid invoices counted as failures.

## Out of scope

- **Removing the reference number from generated payments.** The `Viite`
  / `RF` digits match nothing: invoices carry no reference field, so the
  reference is noise that cannot help and can only dilute the text
  signal. Changing it means regenerating fixtures and reloading the
  production database, so it is proposed separately with measurements
  from `./do eval-matching --compare-reference`.
- Re-tuning the 0.30 / 0.15 status thresholds or the 0.4/0.6 blend
  weights. Both deserve the accuracy measurement first.
- The predict-alternatives tenant leak (`td-20260901082623647538`),
  which affects the same `$why` plumbing but is its own change.
