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

## The candidate domain is the root cause, and it is fixable

The claim above that "`$p` never will be meaningful for a 98k-class
target" was wrong, because it treated the candidate universe as fixed.
It is not. `customer_id` was being passed as *evidence*; the engine also
scopes the candidate universe through the linked path, which is what
`InvoicesTest` and `InvoiceRoutingEvaluation` in aito-core do:

```json
"where":   { "description": ..., "amount": ..., "invoice_id.customer_id": "CUST-0000" },
"predict": "invoice_id"
```

Measured on `env.v2-demo`, the Botnia row:

| variant | `total` (universe) | `$p` | `1/baseP` | latency |
|---|---|---|---|---|
| A current — `customer_id` as evidence | 128 000 | 0.0124% | 97 946 | 26 340 ms |
| B evidence **and** linked-path scope | 16 000 | 0.633% | 41 946 | 7 051 ms |
| C linked-path scope replacing evidence | 16 000 | 0.633% | 41 946 | 2 418 ms |
| D `invoice_id: {$or: [30 ledger ids]}` | 128 000 | 1.41% | 97 946 | 16 416 ms |

Two mechanisms, only one of which scopes:

- **The linked path narrows the universe.** `total` drops to exactly
  16 000, this tenant's invoice count.
- **`$or` on the predict target does not.** `total` stays 128 000 and
  `baseP` is unchanged, so it lands as evidence. There is therefore no
  way to scope down to the 30-row `open_invoices` ledger this way; the
  tenant is the granularity available.

### Accuracy: keep the evidence, add the scope

Top-1 against the fixture's ground-truth link, 24 payments over
`CUST-0000/0001/0002`:

```
A (current)          22/24
B (evidence + scope) 21/24     $p range 1.6e-04 .. 0.664
C (scope only)       16/24     $p range 1.1e-04 .. 0.273
```

C is a real regression — dropping `customer_id` from the evidence loses
signal that the scope does not replace. B is within noise of A at this
sample size while raising `$p` by 10x to 60 000x. Under A, 9 of the 24
correct predictions sat at exactly `1.089e-05`, i.e. flat on the base
rate: the ranking was right and the probability carried no information
at all. Under B the same rows span 0.0001 to 0.66.

**So B is the change to make**, and it is worth making for latency
alone (26.3 s -> 7.1 s here) independently of any display decision.

It does not fully settle the blend question: at the weak end `$p` is
still ~1e-04, where `aito_p*0.5 + 1.0*0.5` remains amount-dominated. It
does mean Aito's number becomes real and quotable on most rows —
"23%, against a 0.002% base rate, out of 16 000 candidates".

## Options

- **Fix the candidate domain (do this first)** — variant B above.
  Better `$p`, better latency, accuracy unchanged. Needs a wider
  accuracy run than n=24 before it ships.
- **Narrow** — include the normalizer in the chain; stop labelling
  decomposition terms as counter-evidence. Independent of the above.
- **Honest blend** — keep the percentage but label the split, so the
  page states how much is Aito and how much is amount matching. Still
  worth doing for the weak rows even after B.
- **Broad** — drop absolute probabilities for rank. Now the weakest
  option: after B the probability carries information, so discarding it
  throws away the thing that was just fixed.

The blend decision touches `docs/demo-script.md` and needs a call, not
just a patch.
