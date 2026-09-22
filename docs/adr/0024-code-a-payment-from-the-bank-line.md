# 0024. Code a payment from the bank line, with no invoice

**Date:** 2026-09-22
**Status:** proposed

## Context

Payment Matching answers "which outstanding invoice does this payment
settle?" It assumes an invoice exists. A real bank feed is full of lines
where none does — direct debits, card settlements, bank charges, payroll,
tax — and those are coded by hand, by someone reading the statement and
choosing a GL account.

That is the workflow the demo currently steps around, and the data to
answer it is already loaded. It needs one v2 capability we have never
used: a join.

```json
{"from": "bank_transactions",
 "fromJoin": {"table": "invoices", "base": "invoice_id",
              "target": "invoice_id", "as": "inv"},
 "where": {"customer_id": "CUST-0000", "description": "<statement line>"},
 "predict": "inv.gl_code"}
```

The joined table's columns are addressed through the alias — `inv.gl_code`,
not `gl_code`, which returns `Field not found`. The join itself is the
learning set: every past payment carries the GL code of the invoice it
settled, so the engine learns "a line that looks like this was coded 4400"
without anyone writing that rule down.

### Measured before designing anything

Each probe **synthesises** a statement line: the vendor fragment the bank
would print, plus a reference number and date that appear nowhere in the
data. This matters. Every real `bank_transactions` row carries its own
`invoice_id`, so querying with a stored description lets the engine
retrieve that row and read the answer off it — the self-retrieval trap
that made ADR 0020's first diagnosis wrong and made ADR 0021's
end-to-end run report 23/23 for a feature contributing nothing. A correct
answer here has to come from the vendor's history.

| tenant | accuracy | baseline | mean `$p` |
|---|---|---|---|
| CUST-0000 | 54/60 = 90.0% | 46.3% (always `4400`) | 0.898 |
| CUST-0007 | 54/60 = 90.0% | 25.0% (always `5100`) | 0.869 |
| CUST-0000, description only | 52/60 = 86.7% | 46.3% | 0.788 |

Two tenants with very different baselines land on the same 90%, and the
description alone carries most of it — the amount is worth about 3
points. So the signal is the vendor text on the statement line, which is
exactly what a human reads.

### What the measurement also exposed

**Our fixtures contain no invoice-less payments.** Every
`bank_transactions` row has an `invoice_id`; that link is how the ledger
is built. So the numbers above measure the hard half — generalising to a
statement line never seen — but the *situation* the page is meant to
depict is not in the data yet.

The page cannot honestly be built without that. A demo that says "this
payment has no invoice" over a payment that has one is the same class of
dishonesty as an equation that does not balance.

## Decision

### 1. Fixtures gain invoice-less bank lines

Roughly 15% of bank transactions become payments with no invoice, drawn
from the kinds an AP clerk actually meets: bank service charges, card
settlements, direct debits for utilities and rent, tax and payroll
transfers. They carry a `gl_code` of their own — the code a human would
assign — and a null `invoice_id`.

That ground truth is what makes the view measurable rather than merely
plausible, exactly as the `invoice_id` link makes matching measurable.

### 2. A Bank Feed view

Lines with no invoice, each with a proposed GL code, its probability, and
the `$why` factors behind it — the same explanation component the other
views use, so a reader sees one vocabulary across the demo.

Coding a line is the user action, and an accepted code is an override
row, like every other correction in this demo.

### 3. Matching and coding are one page's two answers

A statement line is either settling an invoice or is an expense in its
own right. The view runs matching first; when nothing matches above
threshold, it proposes a code instead. That is the actual decision an AP
clerk makes, and it makes the existing matcher's "unmatched" state
useful rather than a dead end.

## Aito usage

- `fromJoin` + `predict` on `inv.gl_code` — new to this project;
  `docs/aito-cheatsheet.md` gains the pattern with the alias gotcha.
- For invoice-less lines the target is `bank_transactions.gl_code`
  directly and no join is needed. The join trains on invoice history;
  the direct predict serves lines that have none. Whether one query can
  do both is an open question for the build.

## Acceptance criteria

- A user sees, for a statement line with no invoice, a proposed GL code
  with a probability and the evidence behind it.
- Accuracy on invoice-less lines is reported per tenant against the
  most-frequent-code baseline, measured on held-out lines rather than
  lines the database contains.
- A line that IS an invoice payment is matched, not coded — the two
  answers do not compete.
- `./do check` covers the new query shape in `aito_check`.

## Demo impact

`docs/demo-script.md` gains the beat that follows naturally from the
matching demo: "and these ones have no invoice at all — Aito codes them
from what you did last time."

## Out of scope

- Learning from corrections within a session. The override table exists
  and closing that loop is its own feature.
- Bank feed ingestion. The fixtures stand in for a bank connection.
- `goal` and `get`, the other two unused v2 capabilities surveyed with
  this one.
