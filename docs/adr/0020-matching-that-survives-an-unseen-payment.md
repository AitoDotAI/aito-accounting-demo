# 0020. Payment matching that survives an unseen payment

**Date:** 2026-09-16
**Status:** proposed

## Context

Payment Matching reports 5 of 8 matched for CUST-0007 on shared 2.9.0.
The three failures are all one vendor, and each has an obvious correct
invoice in the ledger at the same amount — `TXN-000002` → `INV-000006`,
both 14772.29; `TXN-000007` → `INV-000013`, both 10218.0.

The split is clean. **The five that match all carry a `VIITE` reference
number in the bank description. The three that fail carry none.**

Perturbing a working match isolates the cause. Same vendor, same amount,
only the reference digits changed:

```
VIITE 556102546 (real)  -> p=0.969  INV-000003  Restaurant Kimito-Oskar Ab   correct
VIITE 999888777         -> p=0.0038 INV-000179  Entelek Software Oy          wrong
no reference at all     -> p=0.0038 INV-000179  Entelek Software Oy          wrong
```

That token occurs in exactly one row of `bank_transactions` — the row
being predicted, linked to `INV-000003`. The model is recovering the
transaction's own record and reading its `invoice_id` off it. **In
production the payment being matched is not yet in the database, so its
reference is an unseen token and this signal does not exist.** The demo's
headline 0.96 confidence would not reproduce against a real incoming
payment.

Strip the reference and nothing else carries the match. The factor tree
for a failing case shows every piece of evidence inert or negative:

```
baseP 0.0005
exclusiveness            2.31
description "RETAIL"     0.995   <- against
description "MANAGEMENT" 1.000
amount 14772.29          0.999   <- against, despite being an exact amount match
composition nameBoost   23.30    <- decides the answer
```

This is not confined to one tenant. Re-recording
`book/test_04_match.py` live against 2.9.0 moves one of the five CUST-0000
cases to the wrong vendor:

```
AVARN SECURITY OY  Saaja  € 7,113.00  ->  Avarn Security Oy     (recorded baseline)
AVARN SECURITY OY  Saaja  € 7,113.00  ->  Oy Finnish Medical F  (live 2.9.0)
```

The baseline is deliberately **not** accepted, so `./do book` keeps failing
on it until the matcher is fixed. Note the companion book,
`test_predict_vendor_name`, still resolves 5 of 5 correctly — which is the
asymmetry this ADR turns into a design.

The cause is structural. `_predict invoice_id` treats each invoice as an
opaque category and learns `P(evidence | invoice_id = X)` from the
`bank_transactions` rows linked to `X`. **An open invoice has no linked
transactions — that is what makes it open — so no evidence can ever
support it.** Only `baseP` and `nameBoost` separate candidates, and
`nameBoost` picks the wrong vendor.

Two candidate repairs were measured and rejected:

- **`_match` instead of `_predict`.** The cheatsheet presents `_match` as
  the payment-matching endpoint. On a linked column it returns
  byte-identical results — same `$p` to six decimals, same ordering. It
  is the same computation.
- **`invoice_id.vendor` as evidence.** It is a hard, case-sensitive
  filter even inside `_predict`. The exact stored name returns the right
  vendor's invoices; a different case, a partial name, or an unrelated
  payer each return **0 hits**. It cannot carry vendor evidence, and it
  would break the payer-entity case outright.

What *does* work is vendor resolution, because a vendor has many
transactions and so is learnable. All three failing descriptions resolve
correctly, including the degenerate one:

```
RETAIL MANAGEMENT CONSULTING OY TUR / 16.06.25  -> Retail Management Consulting Oy  p=0.999
RETAIL / PVM 13.12.24                           -> Retail Management Consulting Oy  p=0.933
RETAIL MANAGEMENT CONSULTING  Saaja  24.07.25   -> Retail Management Consulting Oy  p=0.999
```

## Decision

### 1. Resolve the vendor first, then rank within it

Replace the single `_predict invoice_id` with two stages:

1. `_predict vendor_name` from the bank description — inference, and the
   stage that carries the demo's actual claim. It generalizes to
   descriptions never seen verbatim, and it is where a payer entity that
   differs from the billed vendor is learned from history.
2. Confine candidates to the resolved vendor and rank within that set.

Stage 1 returns a *stored* vendor name, which is what makes the
exact-equality filter in stage 2 safe rather than brittle: we never filter
on the raw bank string. Stage 1's `$p` becomes the confidence the panel
shows for the vendor step, so a weak resolution is visible instead of
hidden behind a reference-number coincidence.

### 2. Put the reference number on the invoice

Add `reference` to `invoices` (fixtures, schema, loader), carrying the
same value the payment quotes. A real AP system prints the reference on
the invoice and the payer quotes it back; matching reference to reference
is then a **join across two tables**, which survives an unseen payment,
rather than self-retrieval of the payment's own row.

This is the change that makes the strong matches honest. It also gives
the why panel something true to say: "the payment quotes this invoice's
reference".

### 3. Say what the confidence means

The panel currently shows one blended number. It will show the two stages
separately — vendor resolution and invoice selection — because they have
different failure modes and a demo viewer should see which one is weak.

## Aito usage

- `_predict` on `bank_transactions.vendor_name`, evidence = description
  (+ `customer_id` scope). Already exercised by
  `book/test_04_match.py::test_predict_vendor_name`.
- `_predict` on `bank_transactions.invoice_id` with the candidate domain
  confined through `invoice_id.vendor` (exact equality, a stored value)
  and `invoice_id.customer_id` (tenant boundary).
- No new endpoints. Both shapes are in `docs/aito-cheatsheet.md`; the
  `_match` note there needs correcting, since it implies a capability
  `_match` does not have over `_predict`.

## Acceptance criteria

- A user matching a payment whose description carries no reference number
  still sees the correct invoice, for every vendor with payment history.
- When the reference digits of a matched payment are altered, the match
  degrades to the vendor-only result instead of jumping to an unrelated
  vendor.
- The why panel names the vendor resolution and its probability as a
  distinct step, and never shows a factor chain in which every lift is
  <= 1.0 under a high confidence.
- `scripts/evaluate_matching.py` reports repeat-business and cold-start
  as separate splits, and the cold-start split is non-zero.

## Demo impact

`docs/demo-script.md` gains a beat: strip the reference number from a
payment and the match holds on the vendor. That is the thing a CTO in the
room actually wants to see, and today it fails.

## Out of scope

- The payer-entity fixture change (a payer distinct from the billed
  vendor). It depends on stage 1 existing and lands next.
- `nameBoost` deciding a match where every evidence lift is <= 1.0. That
  is engine behaviour; filed separately for aito-core.
- The `String` -> `Text` retype of `invoices.vendor`. Measured as having
  no effect on these factor trees, because the matcher never queries
  `invoices.vendor`.
