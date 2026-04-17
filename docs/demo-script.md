# Demo script

> Canonical walkthrough for the Ledger Pro + Aito demo.
> Run `./do demo` to start.

## Setup

1. Open `./do demo` (opens `ledger-pro-demo.html` in browser)
2. Ensure browser window is wide enough for nav + main + Aito panel

## Walkthrough

### 1. Invoice Processing (default view)

**Story:** 12 invoices pending. Rules handle the known patterns (Telia
= GL 6200, 0.99 confidence). Aito fills the gap — Kesko Oyj gets
routed with 0.94 confidence even though no rule covers it. One invoice
(Unknown Vendor GmbH) falls to human review at 0.31.

- Point out the **Source** column: Rule vs Aito vs No match
- Show the **Rule candidates** tab: patterns mined from 847 unrouted
  invoices, with exact support ratios (47/47, 38/39)
- Highlight the 70% → 91% automation rate in the metrics

### 2. Payment Matching

**Story:** Aito matches invoices to bank transactions by vendor name
similarity, amount proximity, and timing patterns.

- Show matched (green) vs suggested (gold) vs unmatched pairs
- Note the confidence scores on the connector lines

### 3. Smart Form Fill

**Story:** Entering a vendor name triggers multi-field prediction. Gold
fields are Aito predictions with confidence scores.

- Point out GL code, cost centre, approver, payment method, VAT — all
  predicted from vendor history

### 4. Rule Mining

**Story:** The unrouted invoice set is not noise — it contains
unformalized patterns. Aito surfaces them with exact support ratios.

- 47/47 = promote immediately
- 8/9 = strong candidate, review the exception
- 4/11 = not a rule

### 5. Anomaly Detection

**Story:** Inverse prediction — low $p on expected fields = anomaly.
No separate anomaly model needed.

- Duplicate invoice, unusual amount, new vendor high amount

### 6. Quality views

Walk through System Overview → Rule Performance → Prediction Quality →
Human Overrides to show the full feedback loop.

**Key message:** Every human correction feeds back into both the
prediction engine and rule mining. The system gets better with use.

## Aito panel

Note that the right panel updates on every view switch — stats,
operator tags, example query, description, and links all reflect the
current view.
