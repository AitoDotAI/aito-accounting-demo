# Backlog

Live priority order. Move items between sections as work progresses.
Top of `Active` is what's being worked on right now.

## Context

This project is an Aito.ai reference implementation alongside the existing
[aito-demo](https://github.com/AitoDotAI/aito-demo) grocery-store project. The
public reference set lives at `aito-demo/docs/use-cases/`. Our positioning:

- **aito-demo** = e-commerce / grocery use cases (recommend, autocomplete,
  product analytics, etc.)
- **aito-accounting-demo** (this repo) = accounting / AP automation,
  multi-tenant single-table at scale (256 customers, 1M invoices)

When this is publicly released it should be discoverable from the same
front-page library and reuse compatible terminology, branding, and CTA flow.

---

## Active

(nothing in flight — top of the new "r/accounting feedback" section
below has 11 items in priority order)

## Todo (priority order)

### From simulated r/accounting feedback (real-accountant lens)

These came out of running the demo past a simulated r/accounting
thread. Most are sharp but small. Listed in rough order of how often
the same complaint would surface in real conversations.

- [ ] **#21-stretch Liikekirjuri numbering** — replace illustrative
  GL codes with actual Finnish Liikekirjuri (4000s materiaalit,
  5000s henkilöstökulut, 6000s liiketoiminnan muut kulut). Requires
  data regen. **(half day)**

- [ ] **#22-rest Rule-change audit trail (frontend + diff)** —
  schema and endpoints shipped (`rule_revisions` table,
  `POST /api/quality/rules/snapshot`, `GET /api/quality/rules/history?as_of=...`).
  Still to do: Quality/Rules "Compare to date" date picker + diff
  table, scheduled snapshot trigger, JSON/CSV export endpoint.
  **(1-2 days remaining)**

- [ ] **#23 Multi-currency support** — needs data regen + UI work.
  Add `currency` column to invoices/bank_transactions, regenerate
  fixtures with realistic mix (EUR 80%, SEK 5%, USD 8%, DKK 4%,
  GBP 3%), render currency symbol in amount columns, separate
  bank transactions by currency in matching view.
  **(1 day; requires regen)**

- [ ] **#26 Drift over time** — the cynical old partner's question:
  "what does this look like at 90 days?" Now that rule_revisions
  exists (#22), the data path is clear:
  - Group rule_revisions by rule_name; render precision sparkline
    per rule using `valid_from` timestamps
  - Weekly override counts from prediction_log, plotted
  - "Stale rules" section: rules with no recent matching invoices
  Currently the rule_revisions table is empty; needs scheduled
  snapshot (or back-fill on first load).
  **(1-2 days; biggest remaining demo-impact item)**

- [ ] **#27 Multi-entity per customer** — needs schema change.
  Add `entity_id` field to customers and invoices; make customer
  selector a (customer, entity) tree. Predictions scope by
  (customer_id, entity_id) when entity_id is provided, else by
  customer_id alone. **(1 day; requires regen)**

### Architecture / hygiene
(empty — see Done)

### Story / messaging (towards public release)
(all shipped — see Done)

---

## Done

### Phase: P0 — first-minute credibility
- [x] GL labels everywhere (`glDisplay()` helper)
- [x] Decorative buttons removed (+ New Invoice, Export, Save invoice, Promote)
- [x] Panel stats dynamic via `$invoices` marker
- [x] "Touchless rate" replaces "Automation Rate" with honest 0.85 threshold
- [x] Invoice date + Due columns, sorted by due date
- [x] VAT column (Finnish ALV)
- [x] Empty-state guidance instead of "0"
- [x] Realistic Finnish bank descriptions with Viite/RF references

### Phase: P1 — strong positive impression
- [x] SmartField three-state visual (empty / predicted / confirmed)
- [x] Form Fill field reorder; editable invoice date
- [x] Template prediction with "Apply template" one-click
- [x] Anomaly reasons + recommendations (concrete next steps)
- [x] Matching auto-expand first matched row
- [x] Quality / Predictions: rules-only baseline alongside Aito
- [x] Override Patterns: headline finding callout

### Phase: P2 — audit-grade
- [x] Rule statements as sentences with labels and lift
- [x] Rule mining drill-down (matching/disagreeing invoices)
- [x] Quality / Rules: owner + last reviewed columns
- [x] Per-field confidence thresholds
- [x] Submit-time logging to `prediction_log` table
- [x] Anomaly clustering by category

### Big wins
- [x] **#1 Mine rules from data** — per-customer rules from `_relate`
  with support_ratio ≥ 0.95; replaces stale hardcoded RULES list
- [x] **#3 Searchable customer picker** — dropdown grouped by tier
  (enterprise / large / midmarket / small) with search by id, name,
  or tier; current selection highlighted; warm/cold dot preserved
- [x] **#5 Touchless drill-down** — Touchless rate and Review needed
  metric cards are clickable; filter invoice table; active filter
  shown in highlighted banner with "Clear filter ×" button
- [x] **#2 Template-first Form Fill** — landing page shows "Quick start"
  cards for top recurring vendors (template per vendor with GL,
  approver, support count); one click fills all fields including
  vendor; new `/api/formfill/templates` endpoint
- [x] **#4 Data-flow tour** — "Data flow" toggle in TopBar shows
  numbered badges next to UI elements, matched to a "Data flow on
  this page" section in AitoPanel. Each step says what the call
  produces. Implemented on Invoices, Form Fill, Matching, Rule
  Mining, Anomalies.

### Hygiene
- [x] **#7 Frozen demo time** — `DEMO_TODAY = 2026-04-30` is the
  pinned "now" for the whole demo. Backend exposes via
  `/api/demo/today`; frontend `demoToday()` returns it (cached after
  first load, fallback to the same date if API fails). Replaces all
  `new Date()` calls in due-date math and the Form Fill date default.
  Demo behaves like a permanent snapshot — same screenshots, same
  due-soon highlights, every visit.
- [x] **#11 Remove stale single-tenant code** — DEMO_INVOICES,
  DEMO_OPEN_INVOICES, DEMO_BANK_TXNS, DEMO_SCAN_INVOICES, KNOWN_VENDORS
  all deleted. Fallback paths now return empty + error instead of
  fake vendor lists.

### Documentation
- [x] **#15 README + demo-script** rewritten for the multi-tenant
  story. README now leads with the multi-tenant pitch, has the 5-step
  quick-start including PRH fetch, and a per-view table tying each
  view to its Aito call.
- [x] **Public use-case page** — `docs/use-cases/multi-tenant-accounting.md`
  matches the format of aito-demo's existing 11 use-case pages (overview,
  schema, code samples, when-to-use, related references). Ready to drop
  into the public library as the multi-tenant counterpart to the
  single-tenant invoice-processing reference.

### Story / messaging (public release)
- [x] **#16 Above-the-fold framing** — gold gradient strip on every
  page: "Predictive Ledger · multi-tenant AP automation on Aito.ai ·
  N customers · M invoices · same _predict, scoped per customer ·
  zero training". Dismissible, persisted in localStorage.
- [x] **#17 Provable "no training"** — AitoPanel "Verify yourself"
  section with direct links to `/api/schema` (live JSON) and the
  Aito query API reference. Visitors can inspect the actual schema
  and run their own queries.
- [x] **#18 Lift number tooltip** — `<LiftHint>` component renders
  lift values with hover tooltip: "lift = how many times more often
  this combination occurs than random. >20× very strong, 5–20×
  strong, 1–5× weak, <1× anti-correlated." Color-coded by tone.
  Used on Rule Mining and Override Patterns.

### Polish (cold-start)
- [x] **#6 Cold-start onboarding indicator** — when the selected
  customer has < 100 invoices, every page shows an amber banner
  setting honest expectations: "Aito predictions still work but
  with honest low confidence on rarely-seen vendors". CUST-0254 (16
  invoices) is the test case.

### Hygiene (testing)
- [x] **#14 Booktest coverage** — new `book/test_06_template_and_log.py`
  covers: predict_template (joint mode for top vendor),
  mine_rules_for_customer (per-customer mined rules with support and
  lift), prediction_log schema (verifies the audit table exists with
  expected columns). 17/17 booktests pass.

### r/accounting feedback fixes (round 2)
- [x] **#22-partial Rule-change audit trail (schema + endpoints)** —
  new `rule_revisions` table (revision_id, customer_id, rule_name,
  vendor, gl_code, approver, support_match/_total/_ratio, lift,
  valid_from, valid_to, change_reason). New endpoints:
  `POST /api/quality/rules/snapshot` writes the current rule set;
  `GET /api/quality/rules/history?as_of=ts` returns rules valid at
  a given timestamp. Frontend date-picker + diff UI is the remaining
  half (tracked as #22-rest).
- [x] **#24 Bank export format variants** — `format_bank_description()`
  produces six bank-specific layouts (OP, Nordea, Aktia, Danske,
  S-Pankki, Handelsbanken) with realistic per-bank quirks (separator
  styles, all-caps vs mixed, line-length caps, RF vs Viite preference).
  Effective on next data regen (`./do generate-data && ./do reset-data`).
- [x] **#25 Fraud category in anomalies** — new `fraud_signal` cluster
  in the anomaly pipeline. Triggered by round-number amount (≥€10K,
  divisible by 1000) to a vendor with weak prediction history. UI:
  fraud cluster rendered first under a red-bordered header;
  recommendation says "Escalate to compliance / internal audit".
- [x] **#28 Batch override workflow** — Invoices table has a checkbox
  column; selecting rows reveals an action bar with a GL dropdown and
  "Apply override" button. Selected rows highlighted gold; one click
  to clear selection.
- [x] **#29 Integrations page** — new `/integrations` route under a
  "Setup" section in the nav. Shows architectural sketches for
  NetSuite, Dynamics 365 Finance, Procountor, and a generic outbound
  webhook, each with an example payload. Honest "Sketch only" banner
  at the top.

### r/accounting feedback fixes (round 1)
- [x] **#19 "Reference implementation, not a product" notice** — headline
  banner now reads "Predictive Ledger · reference implementation for
  developers building on Aito.ai (not a packaged product) · multi-tenant
  AP demo: …".
- [x] **#20 Reword "Zero training"** — "Zero / Training" stat replaced
  with "Indexed / Model" across all 9 page panels. Headline banner now
  ends with "no separate model file" (concrete) instead of "zero training"
  (marketing-y). aito-cheatsheet.md updated for consistency.
- [x] **#21 Illustrative GL chart disclaimer** — `GL_DISCLAIMER`
  constant added to gl-labels.ts. AitoPanel "Verify yourself" section
  shows a footer note: "GL codes (4100, 5300, 6200…) are illustrative
  — real Finnish Liikekirjuri uses different numbering. Chosen for
  demo readability."

### Polish
- [x] **#8 Progressive skeletons** — new `/api/invoices/raw` endpoint
  returns search-only invoice rows in ~1s. The Invoices page fetches
  raw first (paints id, date, due, vendor, amount, VAT) then overlays
  full predictions when `/api/invoices/pending` returns. Inline
  per-row skeletons in the prediction columns until full data lands.
- [x] **#9 Form Fill banner collapse** — "Aito predicted N fields"
  banner is dismissible via × button; once dismissed it stays gone
  for the session.
- [x] **#10 Anomaly recommendation buttons** — every recommended-
  action block now has working "Mark triaged" (toggles row to
  faded/checked state) and "Copy details" (copies invoice id +
  description + recommendation to clipboard for ticket/email).

### Architecture / hardening
- [x] **#12 Aito client retry + circuit breaker** — `_request` now
  retries once on 5xx and connection errors with 200ms backoff. After
  3 consecutive failures the breaker opens for 30s and subsequent
  calls fail-fast with a helpful error instead of waiting for
  timeouts. State is per-client-instance; success resets the counter.
- [x] **#13 Cache write race** — `cache.compute_lock(key)` returns a
  per-key threading.Lock; concurrent misses for the same key block on
  the same lock, so only one compute runs. Wrapped around the
  invoices and mined-rules cache paths.

### Foundation (earlier)
- [x] 100K invoices, pre-computed predictions architecture
- [x] Multi-tenancy: 256 customers, 1M-capable schema
- [x] Real Finnish company data from PRH YTJ API
- [x] Two-layer cache (in-memory L1 + Aito L2)
- [x] 14 booktests (data sanity, predict, relate, match, evaluate)
- [x] Workflow scripts: fetch-companies, generate-data, load-data,
      precompute, warm-cache
