# Pre-registration: the company link in the invoice queries (ADR 0031 step A)

**Registered:** 2026-10-18, before the run, together with
`scripts/measure_company_link.py`.

## Question

Does adding `vendor_business_id` (the link to the vendor's PRH company
record) to the demo's GL and approver queries change held-out accuracy?
Step A sends the link so that `$why` can explain through the vendor's
industry. It must not cost accuracy.

## Set

- **Tenants:** CUST-0000 … CUST-0019.
- **Rows:** `invoice_id` `$hash` `$mod [40, 7]`, about 2.5% of each
  tenant's invoices.
  - Residue 7 was never an earlier run's test set (those used residue 0).
  - Some rows may overlap earlier test sets by hash coincidence. That does
    not matter here: nothing was tuned on them, and both arms score the
    same rows.
- **Queries:** the demo's own, on main (pooled population, as shipped).
  - GL: `customer_id, vendor, amount, category, description`.
  - Approver: the same inputs, plus `approver.customer_id` and
    `basedOn [role, department]`.
  - Each with and without `vendor_business_id`.

## Decision rule, fixed now

Paired top-1 per held-out invoice, exact McNemar on the discordant pairs,
per target:

- **The link is blocked** for a target if accuracy without it exceeds
  accuracy with it by more than 1 percentage point and p < 0.05.
- **Otherwise it ships** for that target.
- A significant gain is reported, but it is not the reason to ship.

## Run discipline

Read-only, sequential, never 08:00–10:00 Helsinki. One run. Anything that
goes wrong is a dated amendment, and the rule stays.
