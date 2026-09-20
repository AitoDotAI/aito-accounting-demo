# 0020. Rank the open ledger, not every invoice

**Date:** 2026-09-16
**Status:** accepted

## Context

Payment Matching reported 5 of 8 matched for CUST-0007 on shared 2.9.0.
The three failures were all one vendor, and each had an obvious correct
invoice in the ledger at the same amount — `TXN-000002` → `INV-000006`,
both 14772.29; `TXN-000007` → `INV-000013`, both 10218.0.

The split was clean. **The five that matched all carried a `VIITE`
reference number in the bank description. The three that failed carried
none.**

It was not one tenant: re-recording `book/test_04_match.py` against 2.9.0
moved a CUST-0000 case to the wrong vendor as well
(`AVARN SECURITY OY` → `Oy Finnish Medical Fund`).

### A wrong diagnosis, recorded because the test looked decisive

Perturbing a working match — same vendor, same amount, only the reference
digits changed — collapses it:

```
VIITE 556102546 (real)  -> p=0.969  INV-000003  Restaurant Kimito-Oskar Ab   correct
VIITE 999888777         -> p=0.0038 INV-000179  Entelek Software Oy          wrong
no reference at all     -> p=0.0038 INV-000179  Entelek Software Oy          wrong
```

That token occurs in exactly one row of `bank_transactions` — the row
being predicted — which invites the conclusion that the model is
retrieving the payment's own record and reading its `invoice_id` off it.
**The conclusion does not follow.** A reference that no invoice carries
collapses the match under the innocent explanation too, so the test cannot
separate the two.

The discriminating test uses a reference that exists on an invoice but is
quoted by **no** bank transaction — which the fixtures produce naturally,
since a payer quotes the reference only 65% of the time. `INV-000006`
carries `VIITE 50285558` and no transaction mentions it, so self-retrieval
is impossible. The engine still gets it right:

```
description "... VIITE 50285558 ..."  -> p=0.107  INV-000006  correct, rank 1
```

So `invoices.reference` is already Text, the fixtures already put the
vendor's reference on the invoice and have the payer quote it back, and
the engine already joins reference to reference across the link. There was
nothing to build there.

### The actual cause

The matcher asked Aito to rank **every invoice the tenant has ever had** —
about 2000 — and filtered to the open ledger afterwards. So the ~30
outstanding invoices competed against 1970 rows that were never eligible,
and a fixed `limit` truncated the true invoice out of the ranking whenever
nothing sharp (a reference number) pulled it up.

The factor tree showed the symptom: for a failing payment every evidence
lift was ≤ 1.0 — including an amount matching to the cent, at 0.999 — and
`composition:nameBoost` at 23.3× picked the winner, a vendor sharing only
the tokens "Consulting" and "Oy". With 1970 ineligible candidates in the
pool, nothing else was left to discriminate.

Two repairs were measured and rejected, recorded so nobody re-derives them:

- **`_match` instead of `_predict`.** Byte-identical on a linked column —
  same `$p` to six decimals, same ordering. It is the same computation.
- **`invoice_id.vendor` as vendor evidence.** It is an exact,
  case-sensitive filter even inside `_predict`. A different case, a partial
  name, or an unstored payer each return **0 hits**, so it cannot carry
  fuzzy evidence and would break the payer-entity case outright.

## Decision

Scope the candidate domain to the open ledger:

```python
if open_ids:
    where["invoice_id.invoice_id"] = {"$or": sorted(open_ids)}
```

and let the `limit` cover the ledger rather than a fixed cut.

Use the **linked key** `invoice_id.invoice_id`, not the bare predict
target. Both rank correctly, but `$or` on the target itself returns
`invoice_id: null` on every hit after the first, and the matcher reads
that field — it would silently drop candidates. Filed for aito-core as
`td-20260916101358316761`.

This is also the honest framing of the task. The page asks "which
outstanding invoice does this payment settle?", and the outstanding set is
what a real AP ledger hands you. Ranking the settled and cancelled history
alongside it was never the question.

## Aito usage

`_predict` on `bank_transactions.invoice_id`, with the candidate domain
confined through the link:

- `invoice_id.customer_id` — the tenant boundary (ADR 0018).
- `invoice_id.invoice_id` `$or` the open ledger — eligibility.
- `description`, `amount`, `vendor_name`, `customer_id` — evidence about
  the payment.

No new endpoints, no new query type. `$or` on a linked field was fixed
core-side on 2026-08-31 (rev `38a234a6`); before that it was silently
dropped with a 200, which is worth remembering as a shape to test for.

## Consequences, measured

`scripts/evaluate_matching.py --customer CUST-0007 --n 40
--split-on-reference`, same seed and payments before and after:

| split | before | after |
|---|---|---|
| quoted a reference | 21/21 (100%) | 21/21 (100%) |
| **no reference** | **11/19 (57.9%)** | **18/19 (94.7%)** |
| all | 32/40 (80.0%) | 39/40 (97.5%) |

CUST-0000 after the change: 22/22 with a reference, 17/18 without,
39/40 overall.

The probabilities become meaningful rather than merely ordered, because
`$p` is now spread over invoices that could actually be settled:
`KARDEX FINLAND` moves from 0.0708 to 0.9437, `AVARN SECURITY OY` from a
wrong vendor at 0.0000 to the right one at 0.4608. The demo no longer has
to explain why a correct match shows 0%.

## Acceptance criteria

- A payment whose description carries no reference number still finds its
  invoice, for every vendor with payment history. *(18/19 on CUST-0007,
  17/18 on CUST-0000; was 11/19.)*
- `book/test_04_match.py::test_predict_invoice_from_bank_txn` returns
  `Avarn Security Oy` for the `AVARN SECURITY OY` line. *(Does.)*
- The why panel never shows a high confidence over a chain in which every
  lift is ≤ 1.0. *(Not yet verified in the UI — see Out of scope.)*

## Demo impact

`docs/demo-script.md` needs no new beat, but the numbers it quotes change:
matching confidence is now in the 0.3–0.95 range instead of 0.00–0.07, so
any screenshot or script line citing the old figures is stale.

The book now shows both shapes side by side, which makes the point better
than prose: the same five payments, unscoped and scoped.

## Out of scope

- The payer-entity fixture change (a payer distinct from the billed
  vendor). Lands next.
- `nameBoost` deciding a match where every evidence lift is ≤ 1.0. Engine
  behaviour, filed as `td-20260916095541763810`. Scoping the domain makes
  it stop mattering here; it does not make it right.
- The `String` → `Text` retype of `invoices.vendor`. Measured as having no
  effect on these factor trees, because the matcher never queries
  `invoices.vendor`.
- Re-checking the why panel's rendering against the new probabilities.
