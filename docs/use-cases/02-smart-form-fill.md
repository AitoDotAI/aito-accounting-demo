# Smart Form Fill — multi-field prediction

![Smart Form Fill](../../screenshots/02-formfill.png)

*Type any field, the rest predict. Picks vendor → fills GL,
approver, cost centre, payment method, due terms, VAT %. Each
prediction shows top-3 alternatives + `$why`.*

**Companion to [aito-demo's autofill](https://github.com/AitoDotAI/aito-demo/blob/main/docs/use-cases/05-autofill.md)** — same multi-field `_predict` pattern, applied to invoice
entry instead of cart entry.

## Overview

When someone enters an invoice manually, every additional field is
a context clue that should refine the others. Type the vendor:
GL code, approver, cost centre, VAT % all populate. Type the
amount: maybe the approver changes (different threshold). Type the
description: even more signal.

The page demonstrates Aito as a multi-field predictor. One
`_predict` per field, in parallel, conditioned on whatever the
user has typed so far.

## How it works

### The query — one per predicted field

```python
# src/formfill_service.py — predict_fields()
provided = set(where.keys())
fields_to_predict = [f for f in PREDICTABLE_FIELDS if f["field"] not in provided]

with ThreadPoolExecutor(max_workers=8) as pool:
    futures = {field["field"]: pool.submit(client.predict, "invoices", where, field["field"])
               for field in fields_to_predict}
    results = {f: fut.result() for f, fut in futures.items()}
```

`where` is whatever the user has typed; `predict` cycles through
each missing field. Aito returns top-N hits with `$p`, `feature`,
and `$why`.

### Three states per field

Each field renders in one of three states:

1. **Empty** — no user value, no prediction yet
2. **Predicted** — italic + dimmed gold tint, "Predicted N%" label
   below; Tab/blur promotes it to user-confirmed
3. **User** — solid styling, edits are user-entered

The state machine lives in `frontend/components/prediction/PredictedField.tsx`.

### Templates

For repeat-vendor entry, the page also surfaces "quick-start
templates" — vendor-shaped prefill packs derived from each
customer's most-frequent invoice patterns:

```python
# src/formfill_service.py — predict_template()
result = client.predict("invoices",
    {"customer_id": customer_id, "vendor": vendor},
    "gl_code", select=["$p", "feature"])
```

Click "Telia" → form prefills with vendor=Telia, gl_code=6200,
cost_centre=CC-IT, approver=Mikko Laine, etc.

## Demo flow

1. Page loads with empty fields.
2. User clicks the **Vendor** input — top vendors for the active
   customer appear as quick-pick buttons.
3. Click "Telia Finland Oyj" → vendor fills in, then ~150 ms later
   GL code, approver, cost centre, payment method, due terms, VAT %
   all populate with `Predicted N%` labels.
4. User changes the **Amount** to 50 000.00 (unusual for Telia).
   Approver re-predicts to a higher-up signer (CFO instead of
   manager).
5. User clicks the `?` next to the GL code prediction → a popover
   shows the `$why` factor cards, including a description-token
   highlight if a description was entered.

## Aito features used

- **`_predict` with multi-field parallelism** — one query per
  missing field, all running concurrently against the same
  `where` context.
- **`$why` with text highlighting** — same as Invoice Processing;
  drives the "?" popovers.
- **Linked-field selection** — when predicting `approver`, the
  response includes the linked employee's role and department
  for context.

## Performance

Six fields × ~120 ms each in parallel = ~150 ms per "tab out"
event, regardless of which field changed. The frontend debounces
at 250 ms so rapid typing doesn't fire one query per keystroke.

## Out of scope

- **Streaming prediction as the user types.** Right now we wait
  for blur/Tab. A real product might fire on every keystroke for
  fields with `$startsWith` autocomplete (cf. aito-demo's
  intelligent autocomplete).
- **Persisting partial entries.** No drafts; reload loses state.
