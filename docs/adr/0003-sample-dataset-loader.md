# 0003. Sample dataset and data loader

**Date:** 2026-04-17
**Status:** accepted

## Context

The Aito instance is empty. To demonstrate predictions, rule mining,
and anomaly detection we need a realistic Finnish accounting dataset.
The data must be rich enough for Aito to learn patterns, but small
enough to load quickly and for an outside developer to understand by
reading the CSV files.

## Decision

Create a sample dataset as JSON fixture files in `data/`:

1. **`invoices.json`** (~200 records) — the primary table. Fields:
   vendor, vendor_country, category, amount, gl_code, cost_centre,
   approver, vat_pct, payment_method, due_days, description, routed
   (bool), routed_by (rule/aito/human).

2. **`bank_transactions.json`** (~100 records) — bank statement
   entries. Fields: description, amount, date, bank, invoice_id
   (nullable — for payment matching).

3. **`overrides.json`** (~50 records) — human corrections. Fields:
   invoice_id, field, predicted_value, corrected_value,
   confidence_was, corrected_by.

The data follows Finnish accounting patterns: Finnish vendors (Kesko,
Telia, SOK, Fazer, Elisa), realistic GL codes (4100-6200), named
approvers (Sanna L., Mikael H., Tiina M.), standard VAT rates
(24%, 14%, 10%, 0%).

A `src/data_loader.py` script uploads the schema and data to Aito
via the REST API. `./do load-data` runs it. `./do reset-data` drops
and reloads.

## Aito usage

- `PUT /api/v1/schema` — create table schema
- `POST /api/v1/data/{table}/batch` — upload records in batches
- `DELETE /api/v1/data/{table}` — clear table (for reset)

## Acceptance criteria

- `./do load-data` uploads all three tables to Aito in under 30s
- `./do reset-data` drops and reloads cleanly
- After loading, `_predict` on the invoices table returns meaningful
  results (not random — top GL code for Kesko should be 4400)
- Data files are human-readable and self-documenting
- A test verifies the schema definition matches the JSON fixture
  structure

## Demo impact

No visible change to HTML demo yet, but predictions will work once
PR 3 wires the frontend to the backend.

## Out of scope

- Real customer data
- Data generation scripts (fixtures are hand-crafted for demo quality)
- Incremental updates (full reload only)
