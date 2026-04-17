# 0005. Smart Form Fill — multi-field prediction

**Date:** 2026-04-17
**Status:** accepted

## Context

The Smart Form Fill view demonstrates Aito's ability to predict
multiple fields from a single trigger (vendor name). This is the
"wow" interaction: type a vendor name, and GL code, approver, cost
centre, VAT rate, payment method, and due terms all fill in
automatically with confidence scores.

## Decision

### Backend

Add a form fill service (`src/formfill_service.py`) that:

1. Takes a vendor name (and optional amount)
2. Runs parallel `_predict` calls for each target field:
   gl_code, approver, cost_centre, vat_pct, payment_method, due_days
3. Returns all predictions with confidence scores and history counts

A single `POST /api/formfill/predict` endpoint accepts
`{"vendor": "..."}` and returns all field predictions.

### Frontend

The vendor name input triggers predictions on change. When
predictions arrive, each field:
- Gets the predicted value filled in
- Turns gold (predicted styling)
- Shows a confidence annotation below

Fields the user has manually edited are not overwritten on
subsequent predictions. The Clear button resets all fields.

A vendor dropdown with known vendors makes the demo easy to
drive without typing.

## Aito usage

Six parallel `_predict` calls per vendor:
- `predict("invoices", {"vendor": "..."}, "gl_code")`
- `predict("invoices", {"vendor": "..."}, "approver")`
- `predict("invoices", {"vendor": "..."}, "cost_centre")`
- `predict("invoices", {"vendor": "..."}, "vat_pct")`
- `predict("invoices", {"vendor": "..."}, "payment_method")`
- `predict("invoices", {"vendor": "..."}, "due_days")`

## Acceptance criteria

- Selecting a known vendor fills in 6 predicted fields with gold styling
- Each predicted field shows its confidence score
- Unknown vendors produce lower-confidence or missing predictions
- The form works with the backend running (`./do dev`)
- Static mockup remains visible when backend is down
- Tests verify prediction shapes for known and unknown vendors

## Demo impact

The Smart Form Fill walkthrough in `docs/demo-script.md` becomes
interactive. Presenter can select different vendors and see predictions
change in real time.

## Out of scope

- Saving the invoice (no persistence)
- Inline prediction alternatives (dropdown of top-N predictions)
- Input field expansion (postal code → city enrichment) — future PR
