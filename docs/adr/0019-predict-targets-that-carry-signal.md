# 0019. Only offer predict targets that carry signal

**Date:** 2026-09-05
**Status:** accepted

## Context

The coherence audit added in ADR 0018 was extended to score every field
the Quality matrix offers as a prediction target against its own base
rate. Four of six were strong. Two were flat:

| field | accuracy | base rate | gain |
|---|---|---|---|
| category | 100.0% | 45.0% | +55.0 |
| **vat_pct** | **97.5%** | **97.5%** | **+0.0** |
| gl_code | 95.0% | 45.0% | +50.0 |
| approver | 90.0% | 35.0% | +55.0 |
| cost_centre | 82.5% | 55.0% | +27.5 |
| **payment_method** | **55.0%** | **55.0%** | **+0.0** |

Neither flat field is an inference failure. Both are properties of the
fixture, and each is wrong in a different way.

**`payment_method` was `rng.choice(PAYMENT_METHODS)`** — drawn
independently for every invoice, so its 60.4% majority *is* the ceiling
and there is nothing to learn. It was also unrealistic on its own terms:
0 of 32 vendors was paid by a single method, so the same vendor appeared
paid by card, SEPA credit transfer and wire across 1,800 invoices.

**`vat_pct` was `24 unless category == insurance`** — perfectly
learnable, but 98.7% of rows shared one value, so the base rate swallowed
any gain. It was also simply out of date: every 2025 and 2026 invoice
carried 24%.

Both were offered in the matrix's dropdown. A visitor who opened either
saw Aito adding nothing over guessing the majority class, and reasonably
concluded the product was weak — in a repo whose purpose is to convince
that reader otherwise.

## Decision

### `payment_method` is not a prediction target

In an accounts-payable system it is **vendor master data**: set up once
with the vendor's bank details and terms, identical on every invoice from
them. It is a lookup, not an inference, and it does not appear on any
real AP automation's prediction list — which is GL/expense account, cost
centre and dimensions, approver routing, VAT treatment, expense category,
duplicate detection, and whether an invoice can go touchless at all.

Manufacturing signal for it would have invented a use case practitioners
do not have, so instead:

- It is **removed from `predict_targets`**. It stays as an input field
  and as data on the invoice, where it belongs.
- It is now **assigned per vendor** rather than per invoice, so the data
  says what an AP system would say. All 32 vendors are now paid by
  exactly one method.

Note the two changes together make it *trivially* predictable from
vendor — which is precisely why nobody predicts it.

### `vat_pct` becomes date-dependent, which is what makes it worth predicting

Finland raised the standard VAT rate from **24% to 25.5% on 1 September
2024**. This dataset spans 2024-05 to 2026-04, so the change falls inside
the window and the old fixture was both wrong and flat.

The rate is now resolved per invoice by category and issue date:

- exempt (insurance) → `0`
- reduced band (foodstuffs, restaurant services) → `14`
- standard → `24` before 2024-09-01, `25.5` from 2024-09-01

The base rate drops from **98.7% to 75.8%**, so there is real headroom;
and the only way to separate `24` from `25.5` is the invoice date. A
model that gets it right has picked up a regulatory change that nobody
encoded as a rule — a better demo beat than another 99%.

### `cost_centre` follows the expense, not the clerk

Surfaced by the same audit after the two changes above landed, and worth
fixing for the same reason: it was **`COST_CENTRES[processor.department]`
— the AP clerk's own department**. Invoices are only processed by Finance
and Procurement staff, so exactly two of six cost centres ever appeared,
split ~50/50, and *independent of the invoice*: every category divided
evenly between them. Predicting it from vendor/amount/category was
predicting noise, and on a fresh dataset it scored **32.5% against a
50.7% base rate** — actively worse than guessing.

A cost centre is a property of the expense, not of whoever keyed it: a
telecom bill lands on IT's cost centre regardless of which clerk
processed it. It is now derived from the category's owning department,
with 12% cross-charged elsewhere (a laptop bought for the sales team) so
the field is learnable rather than a lookup — the same shape as
`gl_code`, which is ~95% category-determined with a capitalization
exception.

All six cost centres now appear, the base rate is 44.2%, and the ceiling
from category alone is 90%.

Note this field was also *unstable*: an earlier dataset scored it 82.5%
vs a 55% base rate. The generator seeds per-customer RNG with
`hash(customer_id)`, which Python randomises per process, so every
regeneration produced different department assignments and the field's
measured quality swung between 82.5% and below-chance. Deriving it from
the invoice removes that dependence.

### `vat_pct` is typed `String`

It was `Int`, which cannot hold 25.5. It is a tax **code**, not a
quantity: a handful of discrete values, a `predict` target alongside
`gl_code` and `approver`, and nothing arithmetic is done with it. String
is what the other categorical targets already use.

### Measured result

CUST-0000, n=40 per field, in env `v2-refmatch`:

| field | accuracy | base rate | gain | was |
|---|---|---|---|---|
| category | 100.0% | 47.0% | +53.0 | +55.0 |
| payment_method | 100.0% | 66.3% | +33.7 | **+0.0** |
| gl_code | 97.5% | 46.2% | +51.3 | +50.0 |
| cost_centre | 95.0% | 44.3% | +50.7 | **−18.2** |
| approver | 90.0% | 44.6% | +45.4 | +55.0 |
| vat_pct | 82.5% | 75.7% | +6.8 | **+0.0** |

No field is flat, and none is below its base rate. `payment_method` is
now 100% predictable from vendor, which is exactly why it is no longer
offered as a target — it is a lookup.

`vat_pct` gains most of its remaining headroom from the invoice date:
selecting it as an input lifts accuracy 82.5% → 87.5%. It does not go
higher because a raw ISO date is high-cardinality evidence; a derived
period band would make the 2024-09-01 threshold fully learnable, the way
`amount_band` does for amount thresholds. `invoice_date` is now offered
as a selectable input; the derived band is left as follow-up.

## Aito usage

No new query shapes. `vat_pct` moves from an `Int` to a `String` column
and remains an ordinary `_predict` target; `payment_method` remains a
`String` column and an available input, just not a target.

## Acceptance criteria

- The Quality matrix offers no field whose accuracy equals, or falls
  below, its base rate.
- Every cost centre in `COST_CENTRES` appears in the data, and a cost
  centre depends on what was bought rather than on who processed it.
- `./do audit --accuracy` reports no field flagged "no better than
  guessing the majority class".
- Every vendor is paid by exactly one method.
- An invoice dated before 2024-09-01 carries 24%; one dated on or after
  carries 25.5%; food and beverage carries 14%; insurance carries 0%.

## Demo impact

The Quality matrix loses one target and gains a genuinely interesting
one. `vat_pct` is worth demonstrating deliberately: predicting it
correctly requires the invoice date, and the model was never told the
law changed.

## Out of scope

- **Reloading production.** Measured in the copy-on-write env
  `v2-refmatch`; prod still runs the older fixtures. This batches with
  the reference change from ADR 0018 into one reload decision, since both
  need the same regenerate-and-reload and a reload invalidates every
  precompute.
- Adding the prediction targets AP systems do have and this demo does not
  — duplicate detection, project/dimension coding, touchless triage.
  Worth considering separately.
- The reduced 10% band, and the 2025 reshuffle between reduced bands.
  One reduced rate is enough to make the point.
