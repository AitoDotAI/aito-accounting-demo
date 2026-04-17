# 0004. Invoice Processing — live predictions from Aito

**Date:** 2026-04-17
**Status:** accepted

## Context

The Invoice Processing view currently shows hardcoded data. This is the
most important view in the demo — it's where the "70% → 91% automation"
story comes alive. Replacing static rows with live Aito predictions
makes the demo credible and interactive.

## Decision

### Backend

Add an invoice prediction service (`src/invoice_service.py`) that:

1. Takes a set of invoices (vendor, amount, category, etc.)
2. For each invoice, calls Aito `_predict` for GL code and approver
3. Classifies source: invoices matching hardcoded rules get "Rule",
   Aito predictions above confidence threshold get "Aito", the rest
   get "Review needed"
4. Returns enriched invoice objects with predictions and confidence

A simple rules engine simulates the "rules layer" from the demo
narrative. Real rules would come from the customer's system; here
we hardcode a few to show the hybrid architecture.

### API endpoints

- `GET /api/invoices/pending` — returns pending invoices with
  predictions. Uses a set of "demo invoices" that showcase different
  scenarios (high confidence, rule match, low confidence, unknown vendor).

- `GET /api/invoices/metrics` — returns automation rate, avg confidence,
  processed count, exception count computed from the loaded dataset.

### Frontend

The HTML demo fetches from the API on view load. If the API is
unreachable, the static mockup data remains visible (graceful
degradation). A small loading indicator shows while predictions
are being fetched.

## Aito usage

- `_predict` on `gl_code` — per invoice, with vendor + amount + category
  as context fields
- `_predict` on `approver` — same context fields
- Both queries use `select: ["$p", "feature", "$why"]`

## Acceptance criteria

- When the backend is running (`./do dev`), the Invoice Processing
  pending table shows live Aito predictions
- Each row shows: invoice ID, vendor, amount, predicted approver,
  predicted GL code, confidence score, source badge (Rule/Aito/Review)
- Confidence bars reflect actual $p scores
- At least one invoice shows "Rule" source (Telia → GL 6200)
- At least one shows "Review needed" (unknown vendor, low confidence)
- Metrics (automation rate, avg confidence) are computed from real data
- Static HTML still works if backend is not running

## Demo impact

The Invoice Processing walkthrough in `docs/demo-script.md` becomes
live. The demo presenter can now explain that these are real Aito
predictions, not hardcoded values.

## Out of scope

- Rule candidates tab (PR 5: Rule Mining)
- Processed today tab (future)
- Inline editing of predictions
- Pagination
