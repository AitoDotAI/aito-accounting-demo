# 0009. Quality Dashboard — metrics and feedback loop

**Date:** 2026-04-18
**Status:** accepted

## Context

The Quality section has four views showing aggregate metrics about
prediction accuracy, rule performance, and human overrides. These
complete the feedback loop story: predictions → human corrections →
pattern discovery → new rules.

## Decision

Build a quality service (`src/quality_service.py`) that computes
metrics from the invoices and overrides tables:

1. **System Overview** — automation rate breakdown (rules vs Aito vs
   human), prediction accuracy by type, confidence distribution
2. **Rule Performance** — stays static (would need a rules table)
3. **Prediction Quality** — accuracy by confidence band, computed by
   predicting GL codes for known invoices and comparing
4. **Human Overrides** — override counts by field type, emerging
   patterns from override data using `_relate`

Single endpoint `GET /api/quality/overview` returns all metrics.
Frontend updates all four quality views from this data.

## Aito usage

- `_predict` on sample invoices to compute live accuracy stats
- `_relate` on overrides table to find emerging patterns
- `_search` for aggregate counts

## Acceptance criteria

- System Overview shows live automation rate and accuracy bars
- Human Overrides shows real override counts from the overrides table
- Confidence distribution chart updates from real data
- Emerging patterns from overrides use live `_relate` data

## Demo impact

Quality views complete the demo story. Presenter can show the full
loop: predict → override → mine → promote.

## Out of scope

- Rule Performance (keep static — needs rule tracking infrastructure)
- Prediction Quality accuracy-by-band (keep static — needs evaluation
  infrastructure)
- Historical trend data
