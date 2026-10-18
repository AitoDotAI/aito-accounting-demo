# 0031. External company data, and priors on both sides of an explanation

**Date:** 2026-10-18
**Status:** accepted (Antti, 2026-10-18)
**Builds on:** ADR 0027, which parses `$why` linked priors and shows them
as "because" lines.

## Context

An AP clerk does not code an invoice from its vendor name alone. They know
what the vendor *is* (an IT services firm in Tampere) and who on their side
deals with such things (the IT manager, the Tampere office). A predictive
database can learn the same connections when the data links to them, and
can say so in its explanation.

This demo has half of that and shows none of it.

- **External data is already loaded and linked, but unused.**
  - `invoices.vendor_business_id` links to `corporate_entities`: 1,347 real
    Finnish companies from the PRH open-data API (CC BY 4.0), with industry
    code, industry name and registration date.
  - The invoice queries do not send `vendor_business_id`, so the company's
    data never reaches a prediction.
  - No company has a location: `data/fetch_companies.py` dropped the
    addresses the API returns.
  - 9 records have broken text encoding ("CafÚs").
- **Aito already explains through linked rows, on both sides.** Measured
  read-only on shared Aito 2.11.6, 2026-10-18, on one CUST-0000 invoice from
  a software vendor, with `vendor_business_id` added to `where`:

  | prediction | lift | its `linkedPrior` factors |
  |---|---|---|
  | GL 6100 (0.912) | `vendor_business_id` | `vendor_business_id.industry` "Computer programming activities" ×4.16, `industry_code` 62100 ×4.09 |
  | approver EMP-0017 (0.955) | `{vendor_business_id, customer_id}` | `department` "Procurement" ×4.35, `role` "Manager" ×1.88 |

  The first row is an **input-side** prior: what the vendor is. The second
  is a **target-side** prior: what the predicted person is. ADR 0027 left
  target-side priors open ("when the engine emits a prior is not yet
  known"). On 2.11.6 it does. The app parses neither:
  `invoice_service._extract_why_factors` drops `prior`.
- **The fixtures do not contain the connections worth showing.**
  - Approvers are a random manager per category, so the measured
    connection reads "software vendor → Procurement manager". That is
    faithful to the data, but not the story.
  - Employees have no location.

## Decision

Three steps, each its own PR, in this order.

### A. Show the priors Aito already returns (no data change)

1. **Send the company link.** Every invoice prediction (GL, approver,
   form fill, anomalies) adds `vendor_business_id` to `where`. Its
   effect on accuracy is measured first, as a pre-registered held-out
   `_evaluate`, with and without the link, on fresh tenants, scoped per
   tenant (shared is past v2.11.3). It ships only if accuracy does not
   drop beyond the noise.
2. **Keep and show priors on both sides.** This extends ADR 0027's
   parser, which keeps `prior: [{field, value, lift}]` per factor.
   - **Input side**, under the pattern it explains: *"because the
     vendor's industry is Computer programming activities (×4.2)"*.
   - **Target side**, on the predicted value itself: *"Approver: Procurement ·
     Manager"*, with the department and role as highlighted chips, and the
     lift on hover.
   - Linked fields render by their path ("vendor's industry", "approver's
     department"), never as raw `vendor_business_id.industry`.
3. **Leave customer-fact priors out of the UI.** Priors such as
   `customer_id.employee_count` (×8 in the probe) come from the
   cross-tenant leak in ADR 0030. They are kept in the API and folded into
   "other signals" until the tenant-scope work lands.

### B. Real locations for the vendors (external data)

1. **Refetch PRH with addresses.** For each company, take the registered
   address's `postCode`, the Finnish `postOffices[].city`
   (`languageCode` 1) and the `municipalityCode`. All three were verified
   in a live record. Also fix the encoding: the API returns UTF-8, and the
   fetch must not re-decode it.
2. **Optionally link a second external source.** A `municipalities`
   table maps `municipalityCode` to region (maakunta), from Statistics
   Finland's open classification (licence to be confirmed before use).
   This gives a chain of two real public sources: invoice → company (PRH)
   → municipality (Statistics Finland).
3. **Probe before building on the second hop.** Whether `$why` reports
   a prior two links away (`vendor_business_id.municipality.region`) is
   unknown. One read-only query answers it. If it does not, the region is
   stored on the company row instead.

### C. Fixtures that carry the connections (synthetic, stated as such)

Extends ADR 0029's Finnish fixtures, whose `approver_for` is already
role-based.

- Each client company gets one or more offices, each with a city.
  Each employee gets `office_city`.
- Routing follows fit, as in a real AP team:
  - a vendor's industry maps to the department that owns it (IT services →
    IT, freight → Operations, cleaning → Facilities);
  - a vendor in a city where the client has an office goes to that
    office's staff.
- Exceptions stay in: about 10% go elsewhere, so the connections are
  learned, not looked up.
- The README and the pane say plainly that the generator plants these
  connections and Aito discovers them from the data. Nothing is claimed as
  observed customer behaviour.

The two connections the demo should then explain:

    vendor's industry "Computer programming activities"  →  approver's department "IT"
    vendor's city "Tampere"                              →  processor's office "Tampere"

## Aito usage

- `_predict` with a link field in `where` (`vendor_business_id`). Aito
  follows the link and reports the linked row's properties as a
  `linkedPrior` on the lift.
- `_predict` on a link target (`approver` → `employees`) with
  `basedOn: ["role", "department"]`, and `"office_city"` added in step C.
  Aito reports the predicted row's properties as a `linkedPrior` on the
  lifts that favour it.
- Response shape, as measured on 2.11.6:

  ```json
  {"type": "relatedPropositionLift", "value": "<the lift>",
   "proposition": {"vendor_business_id": "0787088-5"},
   "prior": {"type": "linkedPrior", "factors": [
     {"proposition": {"vendor_business_id.industry": {"$has": "Computer programming activities"}}, "value": 4.16}]}}
  ```

  On the target side the factor propositions name the employee's own
  columns (`{"department": "Procurement"}`), not a path.
- New cheatsheet pattern, "Explanations through linked rows". Its
  `aito-check` assertion: for a known software vendor, the GL prediction's
  `$why` carries a `linkedPrior` naming `vendor_business_id.industry`.
- The tenant population (ADR 0030) applies unchanged. The nested `from`
  scopes the invoices, and the linked company rows are shared reference
  data, the same for every tenant, so no tenant data crosses through them.

## Acceptance criteria

- When the GL prediction for an invoice from an IT company is explained,
  the popup shows "because the vendor's industry is Computer programming
  activities" with its lift, highlighted.
- When an approver is predicted, the popup shows the approver's department
  and role as highlighted chips, taken from Aito's target-side prior, not
  from a separate lookup.
- After step C, for a CUST-0000 invoice from an IT vendor, the approver's
  explanation names department "IT". For a vendor in Tampere, the
  processor's explanation names office "Tampere".
- No prior from customer facts (`customer_id.*`) is shown as a reason.
- `vendor_business_id` in `where` does not lower held-out GL or approver
  accuracy beyond the pre-registered margin.
- Every company has a postal code and a city in Finnish, with no broken
  characters (a test over the fetched file).
- `aito-check` asserts the industry prior for a known software vendor.

## Demo impact

`docs/demo-script.md` gains one step on Invoice Processing: open the "why"
for an IT-vendor invoice. The line to say: *"Aito knows this vendor writes
software, from the Finnish trade register, and it knows the IT manager
handles software. Nobody wrote that rule."* Step C changes the fixtures, so
the demo needs a data load and a precompute, both Antti's to run.

## Out of scope

- Live calls to PRH at request time. Data is fetched offline, and the demo
  never depends on PRH being up.
- Fuzzy-matching invoices to companies. Every fixture invoice already
  carries a valid business id; resolving unknown vendors by name is a
  separate feature.
- Using company data for payment matching (ADR 0021 covers the bank line
  naming another company).
- Any claim that the planted connections reflect real accounting practice
  beyond common sense.

## Amendment 1 (2026-10-18): step A measured

- **The company link stays out of the demo's queries for now.**
  - Held out on 1,700 invoices (`docs/notes/company-link-measured.md`,
    pre-registered): GL 93.2% → 92.6% with the link (p 0.12, would ship),
    but approver 79.2% → 73.9% (p 3·10⁻¹⁰, blocked).
  - Sent beside the vendor name, the link adds no visible prior. Aito groups
    the two into one lift (×6.9) with no prior, and the link's own lift is
    1.004.
  - So for a known vendor it costs a little and shows nothing.
- **Where the industry does reach a prediction:** for a vendor the tenant
  has never used, with the link as the only vendor evidence. CUST-0001,
  scoped to its own invoices, gave 4400 0.327 → 0.361, with the industry
  prior ×2.86.
  - It is weak for a data reason, not an engine one. All 1,922 of CUST-0001's
    invoices from that industry come from a single vendor, and one company
    is no industry pattern.
  - Step C's fixtures must give each tenant several vendors per industry
    before the industry is learnable. The link then returns, for new
    vendors and in form fill, with its own measurement.
- **Target-side priors need no new input.** With `basedOn [role,
  department]`, the approver's explanation already carries the predicted
  employee's department (×19.6 in the probe). Step A therefore ships the
  parser and the display, which shows both sides, and `aito-check` asserts
  the engine reports both.
- **Open question:** what a prior on a lift close to 1 means in Aito's
  decomposition. The app drops lifts within 0.05 of 1 as noise, together
  with their priors. Asked of core before any display relies on it.
