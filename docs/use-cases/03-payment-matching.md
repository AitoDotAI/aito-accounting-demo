# Payment matching — bank txn ↔ invoice via schema link

![Payment Matching](../../screenshots/03-matching.png)

*Match incoming bank transactions to open invoices using
`_predict invoice_id` over the schema-linked `bank_transactions`
table. Bank descriptions are messy text; Aito's analyzer handles
the token-level matching.*

**Companion to aito-demo's `_predict` patterns** — but here the
predicted value is a foreign key (`invoice_id`) rather than a
categorical, exercising Aito's schema-link return.

## Overview

Bank statement reconciliation is the most-painful part of AP
operations: the description field is whatever the bank
chose to print, vendors abbreviate, payments combine multiple
invoices, etc. Hand-coded regex falls apart fast.

This view shows Aito's text analyzer doing the matching. The
`bank_transactions` table has an `invoice_id` column linked to
`invoices.invoice_id`. `_predict invoice_id` returns the most
likely invoice for a given (description, amount), with the linked
invoice fields included in the response — no manual join.

## How it works

### Schema link enables single-query joins

```json
// src/data_loader.py
"bank_transactions": {
  "columns": {
    "invoice_id": {"type": "String", "link": "invoices.invoice_id"},
    "description": {"type": "Text", "analyzer": "english"},
    "amount":      {"type": "Decimal"},
    ...
  }
}
```

The `link` makes `invoice_id` a foreign key in Aito's index. When
`_predict` returns it, the linked row is included.

### The query

```python
# src/matching_service.py — match_bank_txn_to_invoice()
result = client._request("POST", "/_predict", json={
    "from": "bank_transactions",
    "where": {
        "customer_id": txn.get("customer_id"),
        "description": txn["description"],   # Text — analyzer matches tokens
        "amount": txn["amount"],
    },
    "predict": "invoice_id",
    "select": ["$p", "invoice_id", "vendor", "amount", "$why"],
    "limit": 5,
})
```

`select: ["$p", "invoice_id", "vendor", "amount"]` — Aito returns
the predicted `invoice_id` and the linked invoice's `vendor` and
`amount` in the same response.

### Match status

The frontend renders one of three statuses per pair:
- **Matched** — bank txn cleanly maps to one invoice
  (top hit p ≥ 0.85, amount within 5%)
- **Suggested** — Aito's top hit looks plausible but isn't strong
  enough to auto-clear (0.5 ≤ p < 0.85)
- **Unmatched** — no high-probability match; user has to find the
  invoice manually or split a payment

## Demo flow

1. Page loads with the customer's recent bank transactions and the
   matched invoice (if any) per row.
2. Click any txn → a popover shows "Why this match?" with the
   `$why` factor cards, including which words in the bank
   description matched (Aito's analyzer runs token-level).
3. Edit a description manually → the prediction re-runs and the
   status badge may change.

## Aito features used

- **`_predict` returning a linked row** via the `invoice_id` schema
  link.
- **Text analyzer on `description`** so vendor abbreviations and
  random punctuation in bank descriptions still match the right
  invoice.
- **`$why` with text highlights** — popover shows which tokens
  drove the match.

## Out of scope

- **Multi-invoice payments.** Each bank txn maps to one invoice.
  A real product would handle one-to-many: a bank txn for €5 200
  might cover three invoices summing to that amount.
- **Bank feed integration.** The demo loads a fixture
  `bank_transactions.json`. Production would consume PSD2 / SEPA
  feeds.
