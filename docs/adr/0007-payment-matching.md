# 0007. Payment Matching — invoice to bank transaction

**Date:** 2026-04-17
**Status:** accepted

## Context

Payment matching pairs open invoices with bank statement transactions.
The challenge: bank descriptions are abbreviated, uppercased, and
inconsistent ("KESKO OYJ HELSINKI" vs "Kesko Oyj"). Amounts may
differ slightly due to fees or rounding.

## Decision

### Matching approach

Use Aito `_predict` to predict the vendor name from a bank
transaction's description text. This leverages Aito's text
similarity capabilities — it has seen historical pairings in the
bank_transactions table where invoice_id links to an invoice vendor.

For each unmatched bank transaction:
1. Predict vendor name from the bank description using `_predict`
   on the invoices table with the bank description as context
2. Find open invoices from that vendor
3. Score matches by amount proximity (within 5% tolerance)
4. Return confidence based on the Aito prediction probability and
   amount match quality

### Backend

`src/matching_service.py` — matching logic with a set of demo invoice
+ bank transaction pairs that showcase different scenarios (exact match,
fuzzy match, amount mismatch, no match).

`GET /api/matching/pairs` — returns matched and unmatched pairs.

### Frontend

The three-column layout (invoices | connectors | bank transactions)
updates with live data. Matched pairs get green styling, suggested
pairs get gold, unmatched stay neutral.

## Aito usage

- `_predict` on `invoices` with bank description to find vendor match:
  `predict("invoices", {"description": "KESKO OYJ"}, "vendor")`
- This works because Aito's Text analyzer handles case normalization
  and partial matching

## Acceptance criteria

- Payment Matching view shows live matched pairs from Aito
- Exact vendor + amount matches show green with high confidence (>0.90)
- Fuzzy matches (close amount, partial name) show gold with medium confidence
- Unmatched pairs show dashed connector with "—"
- Metrics update with real match counts

## Demo impact

Payment Matching walkthrough becomes live. Presenter can explain
that Aito matches "KESKO OYJ HELSINKI" to "Kesko Oyj" using text
similarity, not exact string matching.

## Out of scope

- Manual match/unmatch actions
- Batch auto-matching
- Historical match rate computation
