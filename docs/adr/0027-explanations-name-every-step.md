# 0027. Explanations name every step: the candidate set, and why a pattern points where it does

**Date:** 2026-09-29
**Status:** proposed

## Context

The why panel shows Aito's `$why` as a chain, `base × factors = probability`,
and since #37 the printed chain equals the probability it is printed under.
It balances, but it does not yet *explain*. Two gaps show up in front of an
accountant.

**1. The biggest factor is hidden as "other signals".** On CUST-0001's EL
Finance payment, the panel reads:

```
Base probability   Historical rate for CUST-0001-INV-000019   <0.01%
Other signals      4 normalisation and minor terms, combined   ×363
Pattern match      amount is 12630.06                          ×25
Pattern match      description is … 26.05.25                   ×3.3
                   <0.01% × 363 × 25 × 3.3 = 87%
```

×363 is not minor. It is 312.2 from Aito's `exclusiveness` normaliser. The
docs define it as `1 / sum(p(X_0) + p(X_1) + …)`: it makes the probabilities
of the alternatives sum to one. The other three terms are 1.04, 1.06 and
1.06. The base rate is this invoice's share of the customer's whole invoice
history. The matcher lets Aito choose only among the ~33 invoices in the
open ledger (ADR 0020), and exclusiveness renormalises across those
candidates. So the step that does most of the work reads as "and then a
miracle occurs".

Exclusiveness is not a fixed "1 of N". Its size depends on how strongly the
*other* candidates score. The same payment ranked against a slightly
different ledger (30 candidates, none of them the other shown payments'
invoices) gave exclusiveness ×1.27, and the vendor tokens rose from ×1.06
to ×3.2, because they now discriminated. That is one more reason to state
this step in words rather than fold it.

GL coding has the same term, pulling the other way: ×0.29 for an approver
predict on CUST-0001. That is the competition among the tenant's likely
values.

**2. A pattern says *what* matched, not *why it points here*.** "Description
is TMT-SOFTWARE ×2130" leaves the reader to guess the connection. Aito 2.11
can now say it. A lift may carry a `prior` of type `linkedPrior`, listing
properties of the linked row that account for the lift. Measured on shared
2.11.0 (rev 03b4c2ed), read-only:

```
payment → invoice:  lift ×2130 on description "TMT-SOFTWARE"
    prior ×2130  invoice.description "Software upgrade - version 5.2"
invoice → approver: lift ×1.00 on customer_id CUST-0001
    prior ×15.9  customer_id.name "Ilmarinen Financial Oy Ab"
          ×7.96  customer_id.employee_count 80, …
```

`src/invoice_service._extract_why_factors` drops `prior` today without a
trace, which Prime Directive 2 forbids.

The approver case, "Tiina approves this *because* she is the IT manager",
is what an accountant would find most persuasive. It does not appear. On
the same query no lift carried a prior naming the employee's `role` or
`department`. The fixtures give each category a random manager
(`data/generate_fixtures.py:785`), so there is no department signal to
find. There is a role signal (large amounts escalate to the CEO), but that
lift (×2.2 for Matti Saarinen, CEO) also came back without a prior. When
the engine emits a prior is not yet known.

## Decision

**A. Name the comparison step.** `exclusiveness` stops folding into "Other
signals" and becomes its own line: *"Compared against the N candidates
×312"*. N is the number of alternatives Aito ranked: the open-ledger size
for matching, and the tenant's candidate values for GL and approver.
"Other signals" keeps only terms near 1 (|log10| < 0.1), and its label says
so. If a folded term ever moves the chain by more than ×1.26, the panel
shows it by name instead of folding it; it never hides it.

**B. Show linked priors as a "because" line under their pattern:**

```
PATTERN MATCH  When description is TMT-SOFTWARE                   ×2130
    because the invoice reads "Software upgrade - version 5.2"
```

The parser keeps `prior` on each factor as `prior: [{field, value, lift}]`,
with the link prefix stripped for display. Payment matching comes first,
because Aito already returns priors there. The approver waits on the open
question below and on T2 data that routes by role.

**C. Explicit highlight tags for counter-evidence.** Requests set
`negPreTag`/`negPostTag`, so evidence against a value is styled by our CSS
rather than by the engine's default `<font color="red">`.

## Aito usage

No new query. The same `_predict` with `$why` and `highlight`, plus the
negative highlight tags. New in the response, and handled for the first
time: `relatedPropositionLift.prior` (`linkedPrior`, with factors
`{proposition, value}`), and `normalizer` terms by `name`. Both go into
`docs/aito-cheatsheet.md` with the two measured examples above. An
`aito-check` assertion covers them: a matching explanation for a known
unreferenced payment includes at least one prior.

**Open questions for core, before B goes further.** When does a lift carry
a `linkedPrior`?
- It appeared on a text lift toward a link target (matching) and on an
  input link (`customer_id`).
- It did not appear on `amount_band` toward the approver link, where a role
  signal exists.
- It did not appear on numeric `amount` lifts in matching, even where the
  invoice amount equals the payment to the cent (TMT Software, 12,154.43,
  lift ×3.3). The natural reading of an amount match is an echo prior:
  *"amount is 12,154.43 ← invoice.amount is 12,154.43"*. Should numeric
  lifts carry one, and should a near match (payment 12,630.06 against
  invoice 12,630.56, lift ×24.5) name the invoice amount it matched?

## Acceptance criteria

- On the EL Finance payment, the panel shows *"Compared against 33 open
  invoices ×312"* as its own line, and "Other signals" is ×1.2 or less.
- No folded term exceeds ×1.26 or falls below ×0.79; a larger one is shown
  by name.
- A payment whose description token has a prior shows a "because" line
  naming the invoice's matching property.
- `_extract_why_factors` keeps `prior`. A unit test built from the measured
  response pins it.
- The printed chain still equals the probability (the #37 invariant),
  tested.
- Counter-evidence renders with our CSS class, not `<font>`.

## Demo impact

Step 5 (Payment Matching) gains its strongest line: *"the bank line says
TMT-SOFTWARE, the invoice says Software upgrade: that is the connection
Aito found."* The why panel stops asking the audience to trust a ×363.

## Out of scope

- Approver priors on role/department. Those need T2 fixtures that route by
  role and the answer from core.
- Changing the matcher's amount blend (ADR 0021 note).
- Any change to which candidates are ranked.
