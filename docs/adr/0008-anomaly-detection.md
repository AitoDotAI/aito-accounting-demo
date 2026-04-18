# 0008. Anomaly Detection — inverse prediction

**Date:** 2026-04-18
**Status:** accepted

## Context

Anomaly detection uses Aito's prediction engine in reverse: instead
of asking "what should this field be?", we ask "how surprised is Aito
by this invoice?" Low confidence ($p) on fields that are normally
highly predictable signals an anomaly.

This requires no separate anomaly model — the same `_predict` engine
used for routing and form fill doubles as an anomaly detector.

## Decision

### Approach

For each invoice to scan, predict multiple fields (gl_code, approver,
amount category) and measure how well Aito can explain the data. The
anomaly score is derived from 1 - max($p) across predicted fields.

Curated demo invoices showcase different anomaly types:
- **Unusual amount**: Fazer Bakeries at 10x historical average
- **GL code mismatch**: Kesko Oyj with wrong GL code
- **Unknown vendor + high amount**: first-time vendor, large invoice
- **Normal invoices**: included for contrast (high $p, no flag)

### Backend

`src/anomaly_service.py` — scans invoices using `_predict`, computes
anomaly scores, classifies severity (high/medium/low).

`GET /api/anomalies/scan` — returns flagged transactions sorted by
anomaly score.

### Frontend

Anomaly rows load dynamically with severity icons, descriptions,
and anomaly scores from live Aito data.

## Aito usage

- `_predict` on gl_code with invoice features → $p measures how
  expected the GL assignment is
- `_predict` on approver with invoice features → $p measures how
  expected the routing is
- Low $p across multiple fields = stronger anomaly signal

## Acceptance criteria

- Anomaly Detection view shows live flagged transactions
- Each row has: description, anomaly score, severity badge, amount
- Anomalous invoices score higher than normal ones
- Unknown vendor with high amount flags as high severity
- Metrics update with real counts
- Static mockup remains visible when backend is down

## Demo impact

Presenter can explain: "same _predict engine, used in reverse.
No separate anomaly model needed."

## Out of scope

- Duplicate invoice detection (requires pairwise comparison)
- Time-based anomalies (weekend submission)
- Historical trend analysis
