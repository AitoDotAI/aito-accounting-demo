# 0026. Lead payment matching with payments that quote no reference

**Date:** 2026-09-28
**Status:** proposed

## Context

In Finland (and across SEPA) a supplier prints a reference number on its
invoice — a `viite` or an ISO 11649 `RF` reference — and the payer quotes
it back when paying. When the reference is on the bank line, matching a
payment to an invoice is a lookup. Every AP system already does it, and
nobody needs a model for it.

The work an AP clerk actually spends time on is the rest: payments where
the reference is missing, mistyped, or replaced by free text. The
fixtures model this deliberately — about 35% of payments quote no
reference (`data/generate_fixtures.py`, "The payer quotes the INVOICE's
reference, or quotes nothing").

The Payment Matching page does not show that split. It takes the first
eight payments Aito's `_search` returns for the tenant and sends every
one of them to `_predict`. Measured on CUST-0000, 5–7 of the 8 visible
payments quote a reference. An accountant watching the demo sees Aito
"solving" payments whose answer is printed on the bank line, and
concludes the matcher is doing something trivial. It is the wrong half
of the problem on screen.

It also overstates what Aito is for. On a referenced payment a reader
cannot tell whether Aito ranked the right invoice first or whether the
reference token simply dominated the `$why`. The unreferenced case is
where the claim is real: measured with `./do eval-matching`, Aito picks
the right invoice for 18 of 19 unreferenced payments from vendor name,
description and amount alone.

## Decision

Match in two steps, the way an AP system does, and make the page lead
with the second one.

1. **Reference lookup, no Aito.** If a payment's description contains
   the reference of an invoice in the open ledger, as a whole token after
   normalising case and spacing, it is matched to that invoice. The row
   is shown as **Matched by reference** at confidence 1.0, with no `$why`
   panel, because no prediction was made. This lives in its own small
   module (`src/reference_lookup.py`) so the reader can see that it is
   plain string matching.
2. **Aito for the rest.** A payment with no reference that resolves goes
   to `_predict invoice_id`, exactly as today (ADR 0020, 0021). This
   includes a payment quoting a reference that matches no open invoice.

**Which payments the page shows.** `match_all` fetches a wider window of
the tenant's payments (40) and chooses the eight to show: six that quote
no reference, then two that do. Unreferenced rows come first, and the
first auto-expanded why panel is an unreferenced one. Choosing
*which* payments to display uses the fixture's ground-truth
`invoice_id` link to read each payment's own invoice reference. This
mirrors how the ledger is already built today (see `match_all`'s
docstring). The matcher itself still never sees that link.

The metrics strip splits the count: *N matched by reference · M matched
by Aito · K unmatched*. `./do eval-matching` reports accuracy separately
for referenced and unreferenced payments, so the headline number cannot
be inflated by lookups.

## Aito usage

There is no new query pattern.

- `_search bank_transactions` (existing) with a larger `limit`.
- `_search invoices` for the target rows (existing). The selection now
  also reads the `reference` field, which is already in the schema
  (`src/data_loader.py`).
- `_predict invoice_id` from `bank_transactions` (existing, cheatsheet
  "Payment matching"), now called only for payments the lookup did
  not resolve. That also cuts Aito calls per page load from 8 to about 6.

## Acceptance criteria

- When a user opens Payment Matching, at least the first six rows are
  payments whose bank description quotes no reference, and each shows an
  Aito confidence and a why panel.
- The first auto-expanded why panel belongs to an unreferenced payment.
- A payment that quotes an open invoice's reference shows **Matched by
  reference**, confidence 100%, and no Aito explanation.
- A payment that quotes a reference matching no open invoice goes to
  Aito, not to the lookup.
- The metrics show "matched by reference" and "matched by Aito" as
  separate counts.
- `./do eval-matching` prints accuracy for referenced and unreferenced
  payments separately.
- `./do aito-check` asserts that the visible set contains at least six
  unreferenced payments for each demo tenant.

## Demo impact

Step 5 (Payment Matching) in `docs/demo-script.md` changes. It opens
with a payment that has no reference, and the talk track becomes:
"payments with a reference are a lookup, and we do that without Aito;
these are the ones your AP clerk actually spends the day on." The
auto-expanded why panel now shows vendor-name and description lifts
rather than a reference token.

The precomputed `matching` cache must be rebuilt after deploy
(`./do precompute-v2`).

## Out of scope

- **One payment settling several invoices, partial payments, and cash
  discounts.** These are real and common, but the fixtures contain none,
  and one-to-many matching needs a different selection step than a
  single `_predict`. Each needs its own ADR and fixture change.
- **Fuzzy reference matching** (a mistyped check digit, a transposed
  pair). A near-miss reference falls through to Aito, which is the
  honest behaviour for now.
- Changing the ~35% unreferenced share in the fixtures.
