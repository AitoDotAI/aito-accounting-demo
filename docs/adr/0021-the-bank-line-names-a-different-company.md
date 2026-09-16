# 0021. The bank line names a different company than the invoice

**Date:** 2026-09-16
**Status:** accepted

## Context

Every bank transaction in the fixtures carries
`vendor_name == invoices.vendor`, and its description is a noised form of
the same string. So the hardest thing the matcher is ever asked to do is
see through ALL CAPS, a dropped `OY`, or a city suffix.

That is not the case an AP clerk spends their day on. The money often
moves under a name that is not the one on the invoice:

- the vendor bills under a **trade name** and settles as a **legal
  entity** — an invoice from "Aito.ai", a bank line reading "EPISTO OY";
- the receivable has been **factored**, so a finance company collects;
- a group **parent or shared treasury** receives on a subsidiary's behalf.

In all three the name on the bank statement is one the AP system has
**never seen in its vendor master**. String similarity cannot help,
because there is no similarity — "Episto" and "Aito" share nothing. Only
history can: this tenant has paid invoices from that vendor before, and
those payments arrived under that other name.

That is the specific claim this demo exists to make, and today's fixtures
cannot exercise it.

## Decision

Give roughly 20% of each customer's vendors a **settlement entity**
distinct from the billed name. `bank_transactions.vendor_name` and the
description carry the settlement entity; `invoices.vendor` keeps the
billed name. The `invoice_id` link remains ground truth.

Three kinds, so the demo is not one trick:

| kind | invoice says | bank line says |
|---|---|---|
| `legal_entity` | a trade name | the legal entity behind it |
| `factoring` | the vendor | a finance company collecting |
| `group_treasury` | a subsidiary | the group parent |

The settlement entity is **not** added to `corporate_entities`. Its
absence from the vendor master is the point: the name arriving from the
bank is one nothing in the system can look up.

### Keeping the regeneration cheap

The settlement entity is drawn from a `random.Random` seeded on the
vendor's `business_id`, not from the shared per-customer stream. Adding
draws to that stream would shift every downstream value and change all
128,000 invoices, forcing a full reload. Keyed independently, `invoices`
regenerates byte-identical and only `bank_transactions` (17 MB) reloads.

### Reporting

`scripts/evaluate_matching.py` gains a split on whether the bank line
names the billed vendor. Reporting one blended number would hide exactly
the case this ADR adds — and the existing `--split-on-reference` already
establishes the pattern that a matcher's accuracy is meaningless unless
you say which case it was measured on.

## Aito usage

No new query shapes: `_predict bank_transactions.invoice_id`, scoped to the
open ledger (ADR 0020). But the claim that it *learns* the settlement
association turned out to be false as written, and fixing it needed a
schema change.

### Measured: with `vendor` as `String`, the association does not exist

Control: same ledger, same amount, same description shape — only the
bank-side name changes. **A** = the vendor's own settlement entity.
**B** = a settlement entity belonging to an unrelated vendor. Target is an
invoice with **no** linked payment, so nothing can be retrieved directly.

```
                                  A: own settler   B: other    rank A / B
Avarn Security Oy                        0.02846    0.02846      35 / 35
Tailio Design Oy                         0.02845    0.02845      35 / 35
Kiinteistö Oy Törmäniityntie 14          0.02929    0.02929      28 / 28
```

Identical to five decimals. The engine uses a linked table's column as a
feature only if it is **tokenized** — which is why a reference quoted by
no transaction still retrieves its invoice (ADR 0020): `reference` is
`Text`. `vendor` was `String`, one atomic symbol, and carried nothing.

An end-to-end accuracy run did **not** reveal this. It reported 23/23 on
the settlement split, because the matcher blends Aito's `$p` with a
client-side amount score and the amount was doing all of the work. Only
the control, which holds the amount fixed and varies one field, separates
them.

### Measured: tokenized, it works — and breaks rule mining

Retyping `vendor` to `Text`:

```
                                  A: own settler   B: other    rank A / B
Avarn Security Oy                        0.37871    0.01606       1 / 19
Tailio Design Oy                         0.57448    0.02337       1 / 17
Kiinteistö Oy Törmäniityntie 14          0.60483    0.01451       1 / 26
Oy Lux Logistics Ab                      0.13180    0.00920       2 / 33
```

But CUST-0007 went from 20 mined rules to **0**, because `$patterns` on a
`Text` column returns the vendor decomposed into per-token clauses:

```
String:  {"$and": [{"vendor": "Re - Copiers Oy"}, {"category": "telecom"}]}
Text:    {"$and": [{"vendor": {"$has": "re"}},
                   {"vendor": {"$has": "copiers"}}, {"category": "telecom"}]}
```

`vendor $has "re"` is not a business rule, and `parse_conjunction` drops
it. Both lifts are 45.62 — the statistics are the same, the *legibility*
is not.

### Decided: carry the name twice

`vendor` stays `String` and `vendor_text` is added, same value, `Text`.
Two features want opposite types of one column; giving them one column
each is cheaper than making either worse. With both, the association
numbers above are unchanged and rule mining is back to 20 candidates.

A denormalised duplicate in a reference project needs justifying, and the
justification is in the schema comment: it is not redundancy for
convenience, it is one column per access pattern.

**This should be temporary.** Aito indexes a Text column's distinct whole
values *and* its distinct tokens separately, so `$patterns` has the
information to propose `vendor = "Re - Copiers Oy"` and simply does not.
Filed as `td-20260916122259713206`, with the sharper form of the argument:
the token conjunction is not merely uglier, it is **wrong** where one
vendor's tokens are a subset of another's —

```
vendor      = "Kauko Oy"                  245   the truth
vendor_text $has "kauko" AND $has "oy"    331   what $patterns mines
vendor      = "Kauko Group Oy"             86   absorbed silently
```

— so a mined rule's displayed support inflates by 35% and conflates two
legal entities. When that lands, `vendor_text` should be deleted and
`vendor` retyped to `Text`.

## Acceptance criteria

- A payment whose bank line names a settlement entity, for a vendor with
  prior payment history, is assigned to the right invoice.
- The same payment for a vendor with **no** prior history is not, and the
  demo says so rather than reporting a blended average.
- `evaluate_matching` reports same-name and settlement-entity splits
  separately, each with its own n.
- No change to accuracy on the same-name split.
- Rule mining still produces its candidates (20 on CUST-0007).

## Demo impact

`docs/demo-script.md` gains the beat the product claim actually needs:
a bank line naming a company that is nowhere in the vendor master, and
Aito assigning it correctly from history.

## Consequences, measured

`evaluate_matching --customer CUST-0000 --n 140 --no-reference
--split-on-settlement` on the branch:

| split | n | accuracy | mean confidence |
|---|---|---|---|
| bank line names the billed vendor | 117 | 95.7% | 0.64 |
| bank line names a settlement entity | 23 | 100% | 0.62 |

The settlement split scoring *higher* is not a win, it is the amount score
again: with `n=23` and every amount near-unique in a 170-invoice ledger,
this number cannot distinguish a working model from a broken one. The
control above is the measurement that can. Mean confidence on the
billed-vendor split rising from 0.52 to 0.64 is the part attributable to
the model.

Three of the eight controlled cases still fail: Investra → Intrum (102
prior payments), Intermodal → Aktiv Kapital (118), Cafetering → Svea (82).
They share no token with their settler and have the least history. The
five that work either share a token (Avarn/Avarn, Tailio/Tailio,
Kiinteistö/Kiinteistö) or have substantially more history (Lux Logistics →
Svea Ekonomi, 285 payments, shares nothing, rank 2). So the honest demo
claim is **"Aito learns this from history, and needs enough of it"**, not
"Aito always gets it".

## Out of scope

- Adding settlement entities to `corporate_entities` or to any
  vendor-resolution UI. They are deliberately unknown to the system.
- Changing `invoices`. The billed name does not move.
