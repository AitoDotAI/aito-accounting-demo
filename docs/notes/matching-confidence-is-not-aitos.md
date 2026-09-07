# The payment-matching confidence is not Aito's number

Measured 2026-09-07 against `env.v2-demo`, `CUST-0000`, the Botnia row
(`CUST-0000-INV-000002`, payment and invoice both €1 756,00).

## What Aito actually returns

Raw `$why` for the top hit of `_predict invoice_id`:

```
baseP                                                    1.020971e-05
product(exclusiveness 2.0018 x trueFalseExclusiveness 1.0 x rowCap ~1.0)
relatedPropositionLift  {amount: 1756.0}                     0.028242
relatedPropositionLift  {$group: [amount 1756.0,
                                  description "24022026"]}  28.285903
relatedPropositionLift  {description: "745074511"}           7.607825
                                                         ────────────
$p                                                       1.2421e-04
```

The factors multiply to `$p` exactly, so nothing here is broken.

## Three things this shows

**1. The base rate is genuine, and so is the final probability.**
`1/1.021e-05 = 97 946` — a prior over the whole instance's invoice
population (128 000), not this tenant's 16 000, because the candidate
domain for a predict target is global while `customer_id` only supplies
evidence. All the evidence together moves the invoice **12.2x above its
base rate**, ending at 0.0124%. For a link target with ~100k classes
that is what the arithmetic gives; the UI's `<0.01% x ... = <0.01%` is
telling the truth.

**2. The 0.50 on screen is ours, not Aito's.** From
`match_bank_txn_to_invoice`:

```
combined = aito_p * 0.5 + amt_score * 0.5
         = 0.000124 * 0.5 + 1.0 * 0.5
         = 0.500062
```

Aito contributes **0.0124%** of the displayed confidence. To four
decimal places the headline number on a page titled "Aito _predict
invoice_id via schema link" is the amount-proximity heuristic alone.
The stale August bundle hid this by printing the blend at the end of
Aito's chain (`0% x 28.3 x 0.0 = 48%`); once the chain terminated
honestly, the gap became visible.

**3. Two rendering defects fell out of the same tree.**

- `_extract_why_factors` drops the nested `type: product` normalizer
  group, so the displayed chain is short by exactly 2.0018x and does
  not reproduce `$p`, while being presented as a complete decomposition.
- The standalone `amount` term (lift 0.028) renders as red
  COUNTER-EVIDENCE on a row where the amount matches to the cent. It is
  a double-counting correction — `amount` already appears inside the
  28.3x group factor — not evidence against the match. Treating every
  lift < 1 as counter-evidence is our rule, and it misleads here.

## Options

- **Narrow** — include the normalizer in the chain; stop labelling
  decomposition terms as counter-evidence.
- **Broad** — stop showing absolute probabilities on this page. For a
  98k-class link target, rank is the meaningful output and `$p` never
  will be. "12x more likely than base, top of 98 000 candidates" is both
  true and stronger than "0.01%".
- **Honest blend** — keep the percentage but label the split, so the
  page states how much is Aito and how much is amount matching.

The third changes what the demo claims and touches
`docs/demo-script.md`; it needs a decision, not just a patch.
