# 0012. Single-table multi-tenancy via `where customer_id`

**Date:** 2026-04-26
**Status:** accepted

## Context

The demo started single-tenant — one fictional accounting company,
~16K invoices, all served from one Aito table. To be a credible
reference for SaaS adoption we needed multi-tenancy: many customer
companies, each with their own vendors / employees / GL coding
policies, hosted on a single shared Aito instance.

There are three common architectures:

1. **Per-tenant database.** Each customer gets their own Aito
   instance. Strong isolation, easy to reason about, but operations
   pain (255 instances to provision, monitor, back up, scale).
2. **Per-tenant table.** One Aito instance, N tables (one per
   tenant). Schemas have to be kept in sync across tables; queries
   that span tenants (admin views, benchmarks) are hard.
3. **Single shared table with a `customer_id` column.** Everything
   in one table, every query carries `where customer_id = …`.

For a relational warehouse (Postgres, Snowflake) #3 is the obvious
choice for a public SaaS at this scale. But Aito is a *predictive*
database — adding `customer_id` to a `where` clause changes the
conditional probability, not just the row set. The question is
whether predictions stay scoped per-tenant.

## Decision

Single shared table with a `customer_id` column on every row. Every
service-layer call adds `customer_id` to the `where` clause:

```python
client.predict("invoices",
    {"customer_id": "CUST-0000", "vendor": "Telia Finland"},
    "gl_code")
```

This carries through every operator the demo uses: `_search`,
`_predict`, `_relate`, `_evaluate`, `_recommend`. The same vendor
in two different customers' history yields *different* predictions
because Aito only computes the conditional probability over rows
that match the where filter.

Every API endpoint takes `customer_id` as a query parameter; the
service layer threads it down to Aito. There is no per-tenant code
path — the where clause is the only mechanism.

## Aito usage

The same operators we already used, with `customer_id` added to
every `where`:

```javascript
{from: "invoices", where: {customer_id: "...", vendor: "..."}, predict: "gl_code"}
{from: "invoices", where: {customer_id: "...", category: "telecom"}, relate: "gl_code"}
{from: "invoices", where: {customer_id: "..."}, limit: 20}
```

The `customer_id` column is indexed, so the where filter is
O(log n) on the constraint columns. Measured on the 128K-invoice
dataset (warm connection):

| Operator | latency | notes |
|----------|---------|-------|
| `_search` 20 hits | ~85 ms | flat across customer sizes |
| `_predict` gl_code | ~120 ms | conditional on per-customer history |
| `_relate` 5 hits | ~80 ms | per-customer pattern mining |

## Acceptance criteria

- Every API endpoint scopes its query to a single customer via
  `customer_id`.
- Two customers using the same vendor receive *different* GL-code
  predictions, reflecting their respective routing histories.
- Switching customers in the topbar updates every view (predictions,
  matching, anomalies, quality) without a page reload.
- A customer with 0 invoices loads cleanly with empty states, not
  errors.
- No per-tenant Aito table or code path exists.

## Demo impact

Replaces the original single-tenant story with the SaaS one. The
topbar customer switcher becomes the demo's headline gesture: same
vendor, different customer, different prediction.

The geometric size distribution (3 enterprise, 12 large, 48
midmarket, 192 small) lets the same demo prove both ends of the
spectrum — 16K-invoice customer at 99% accuracy, 125-invoice
customer with honest low-confidence cold-start predictions.

## Out of scope

- **Tenant-level access control.** The demo doesn't authenticate;
  any visitor can switch to any customer. A real product would
  enforce `customer_id` server-side from the user's session, not
  from a query parameter.
- **Cross-tenant queries.** Admin views (e.g. "show me overrides
  across all customers") are not in the demo. The where-clause
  filter would just be omitted, but no view exercises that path.
- **Tenant isolation guarantees.** A bug that drops `customer_id`
  from a where clause would return all-tenants data. The
  validate_customer_middleware catches missing/empty values, but
  doesn't guard against an endpoint that forgets to thread
  `customer_id` through.
