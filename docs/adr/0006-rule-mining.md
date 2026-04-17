# 0006. Rule Mining — `_relate` integration

**Date:** 2026-04-17
**Status:** accepted

## Context

Rule Mining is the key differentiator in the demo narrative: Aito
doesn't just predict — it discovers patterns that can become explicit
rules. The Rule Mining view shows patterns mined from invoice data
with exact support ratios (e.g. "category=telecom → GL 6200, 17/17").

## Decision

### Backend

Add a rule mining service (`src/rulemining_service.py`) that:

1. Runs `_relate` queries for each condition field (vendor, category,
   vendor_country) against gl_code and approver targets
2. Extracts support ratios from `fs.fOnCondition` / `fs.fCondition`
3. Classifies patterns as Strong (≥95%), Review (≥75%), or Weak (<75%)
4. Computes coverage as fCondition / total records

`GET /api/rules/candidates` returns mined rule candidates sorted
by support ratio.

### Frontend

The Candidates tab in the Rule Mining view loads live data from the
API. Each row shows the condition pattern, target prediction, support
ratio, coverage, strength badge, and action button.

## Aito usage

- `_relate` on `invoices` table with single-field conditions
  (vendor, category, vendor_country) against gl_code target
- Support ratio from `fs.fOnCondition / fs.fCondition`
- Coverage from `fs.fCondition / fs.n`

Example response hit:
```json
{
  "related": {"gl_code": {"$has": "6200"}},
  "condition": {"vendor": {"$has": "Telia Finland"}},
  "lift": 10.7,
  "fs": {"fOnCondition": 6, "fCondition": 6, "n": 230}
}
```
→ Pattern: `vendor="Telia Finland"` → GL 6200, support 6/6, coverage 2.6%

## Acceptance criteria

- Rule Mining candidates tab shows live patterns from Aito `_relate`
- Each pattern has: condition, target GL code, support ratio, coverage %,
  strength badge (Strong/Review/Weak)
- Patterns sorted by support ratio (strongest first)
- Metrics update: candidate count, strong count, total coverage gain
- Static mockup remains visible when backend is down
- Tests verify pattern extraction, classification, and sorting

## Demo impact

Rule Mining walkthrough uses real Aito data. Support ratios like
"17/17" and "33/34" are from actual dataset statistics, not hardcoded.

## Out of scope

- Promote/dismiss actions (no persistence layer yet)
- Active rules and dismissed tabs (keep static for now)
- Multi-field conditions (vendor + category combined)
- Approver as relate target (GL code only for now)
