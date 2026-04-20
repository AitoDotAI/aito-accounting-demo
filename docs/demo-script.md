# Demo script

> Canonical walkthrough for the Predictive Ledger + Aito demo.
> Start: `./do dev` then open http://localhost:8200 in a browser.

## Setup

1. Ensure `./do load-data` has been run (sample data in Aito)
2. Start backend: `./do dev` (port 8200)
3. Open http://localhost:8200 — look for the green "Live" indicator
4. Browser window should be wide enough for nav + main + Aito panel

## Key narrative

**The 70% → 90% gap.** Rules-based automation tops out at ~70%. The
remaining 30% is too sparse or contextual to write rules for. Aito
fills this gap without replacing rules. The demo shows the hybrid
architecture and the feedback loop that makes it self-improving.

## Walkthrough

### 1. Invoice Processing (default view)

**Story:** 12 invoices pending. Rules handle known patterns (Telia =
GL 6200, 0.99). Aito fills the gap — Kesko Oyj gets routed with 0.91
confidence even though no rule covers it. Unknown Vendor GmbH falls
to human review at 0.29.

- Point out the **Source** column: Rule (blue) vs Aito (gold) vs
  No match (amber)
- Highlight the **92% automation rate** — up from ~25% rules-only
- Note confidence scores: Aito is honest about uncertainty

**Aito operator:** `_predict` for GL code and approver

### 2. Smart Form Fill

**Story:** Type a vendor name → 6 fields predict automatically. Gold
highlighting shows which fields Aito predicted.

- Select **Kesko Oyj** from dropdown — all 6 fields fill at 0.95 avg
- Clear and select an **unknown vendor** — lower confidence shows
  Aito's honest uncertainty
- Point out the confidence annotations below each field

**Aito operator:** `_predict` (6 parallel calls per vendor)

### 3. Payment Matching

**Story:** Bank statements say "KESKO OYJ HELSINKI" — how do you match
that to invoice vendor "Kesko Oyj"? Aito's `_match` traverses the
link between tables.

- Green = matched (Telia, Kesko exact)
- Gold = suggested (Fazer partial match)
- Dashed = unmatched (Verkkokauppa, no bank txn)

**Aito operator:** `_match` (traverses schema links)

### 4. Rule Mining

**Story:** Unrouted invoices aren't noise — they contain patterns.
Aito surfaces them with exact support ratios.

- `category="supplies" → GL 4400, 33/33` — promote immediately
- `category="telecom" → GL 6200, 17/17` — another obvious rule
- Support ratios come from Aito statistics, not ML estimates
- An accountant can verify without ML literacy

**Aito operator:** `_relate` (feature-level statistics)

### 5. Anomaly Detection

**Story:** Same `_predict` engine, used in reverse. Low confidence on
predictable fields = anomaly signal. No separate anomaly model.

- GL code mismatches: "predicted 4400 but stated 5100"
- Unknown vendors: low confidence across all fields
- Point out: **zero additional infrastructure** — same API

**Aito operator:** `_predict` (inverse — low $p = anomaly)

### 6. Quality views

**System Overview** — live automation breakdown: rules 15%, Aito 63%,
human 9%. Shows the gap rules leave and how Aito fills it.

**Human Overrides** — 44 corrections, mostly GL code (29). Every
override is mined for patterns via `_relate`. This closes the loop:
predict → override → discover → promote.

**Aito operator:** `_search` (aggregates), `_relate` (patterns)

## Aito panel

The right panel updates on every view switch — stats, operator tags,
example query, and links all reflect the current view. Point this out
to technical audiences: it shows the actual Aito query being used.

## Key messages

1. **Zero training time** — queries run immediately on ingested data
2. **Hybrid architecture** — rules for known patterns, Aito for the rest
3. **Honest uncertainty** — Aito says "I don't know" (low $p) rather
   than guessing confidently
4. **Self-improving** — human corrections feed back into predictions
   and rule mining
5. **Single engine** — `_predict`, `_match`, `_relate` cover routing,
   matching, mining, and anomaly detection
