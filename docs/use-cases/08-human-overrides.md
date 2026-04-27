# Human overrides — input → output rules from corrections

![Human Overrides](../../screenshots/09-quality-overrides.png)

*Two-pass `_relate` on the overrides table. Pass 1 finds the
most-corrected target values; pass 2 walks the schema link to
`invoices.vendor` to surface the input feature that drove the
correction.*

## Overview

When a controller corrects a predicted GL code, that's data —
specifically, "given this invoice's input fields, the model's
prediction should have been X". The overrides table stores those
events; `_relate` mines them for emerging rule candidates.

The headline shape we want is:

```
vendor=Talotilit Oy → gl_code corrected to 5400  (12 cases, 8.2× lift)
```

Same shape as Rule Mining's output — promotable directly into the
rules table.

## How it works

### Pass 1: which target values are over-corrected?

```python
# src/quality_service.py — compute_override_patterns()
client.relate("overrides",
    {"customer_id": customer_id, "field": "gl_code"},
    "corrected_value")
```

Returns ranked `corrected_value` values: which GL codes are
showing up most often in corrections. Marginal — doesn't tell us
*why*.

### Pass 2: what input drove each correction?

For each top corrected_value, walk the schema link to the linked
invoice's vendor:

```python
client.relate("overrides",
    {
        "customer_id": customer_id,
        "field": "gl_code",
        "corrected_value": corrected,
    },
    "invoice_id.vendor")     # linked-field traversal
```

`invoice_id.vendor` is Aito's link traversal: `overrides.invoice_id`
→ `invoices.invoice_id` → `invoices.vendor`. The relate pulls back
the vendor most-strongly associated with corrections to that
target value.

### Combining the two passes

Each output row carries both the marginal target and the input
driver:

```json
{
  "field": "gl_code",
  "corrected_to": "5400",
  "input_field": "invoice_id.vendor",
  "input_value": "Talotilit Oy",
  "count": 12,
  "lift": 8.2
}
```

Frontend renders `vendor = "Talotilit Oy" → gl_code corrected to
5400` with the same row template as Rule Mining.

## Demo flow

1. Page shows 5–8 emerging patterns ranked by lift.
2. Each row reads as a rule candidate: input → output, support
   count, lift.
3. Promote → entry lands in the rules table; next prediction
   short-circuits via the rule path.

## Aito features used

- **`_relate`** — the rule-discovery operator, twice in series.
- **Schema link traversal** — `invoice_id.vendor` walks from
  `overrides` to `invoices.vendor` without a manual join.
- **Customer scoping** — same `customer_id` constraint as
  everywhere else; emerging patterns are per-tenant.

## Out of scope

- **Per-user override patterns.** All corrections are
  customer-scoped, not user-scoped. Real product might want "this
  particular controller corrects vendor X's GL more often than
  others — maybe that's wrong".
- **Active learning loop.** No automatic re-prediction of
  similar invoices when a rule candidate emerges. Manual promote
  → next predict cycle picks it up.
