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

- [ ] **#19 "Reference implementation, not a product" notice** —
  the headline banner currently reads like product marketing. Add a
  small "Reference implementation for developers building on Aito —
  not a packaged product" line under the gold strip, or expand the
  banner copy. **(15 min)**

- [ ] **#20 Reword "Zero training"** — multiple commenters read it
  as vapor-marketing. Replace with something concrete:
  "Predicts directly from indexed data — no separate model file".
  Affects every AitoPanel stat block plus the headline banner.
  **(20 min)**

- [ ] **#21 "Illustrative GL chart" disclaimer** — GL codes 4400 /
  5100 / 6200 are made-up numbers, not real Finnish Liikekirjuri /
  FAS. A real auditor noticing this loses trust. Add a small
  "Illustrative chart of accounts" tooltip or footer line on every
  view that displays GL codes. **(15 min)**
  - Stretch: actually re-map fixtures to Liikekirjuri numbering
    (4000s materiaalit, 5000s henkilöstökulut, 6000s liiketoiminnan
    muut kulut, 7000s poistot). **(half day, requires regen)**

- [ ] **#22 Rule-change audit trail** — current Quality/Rules has
  Owner + Last reviewed but no history of changes. SOX teams need
  "show me the rule set as of 2025-Q3 and the diff to 2025-Q4". Add:
  - `rule_revisions` table: rule_id, customer_id, vendor, gl_code,
    approver, support_ratio, lift, valid_from, valid_to
  - "Compare to date" picker on Quality/Rules
  - Export as JSON/CSV
  **(2-3 days; high value for SOX/audit conversations)**

- [ ] **#23 Multi-currency support** — currently EUR everywhere.
  At least: add a `currency` field to invoices, show the symbol in
  amount columns, group bank transactions by currency. Most
  multi-tenant SaaS customers have entities in 4+ currencies.
  **(1 day; hidden assumption that bites in real demos)**

- [ ] **#24 Bank export format variants** — current bank
  descriptions use one generic format. Real OP / Nordea / Aktia /
  Danske / S-Pankki have distinct layouts:
  - OP: `<vendor> / VIITE <num> / PVM <date>`
  - Nordea: `<vendor> <date> Saaja <iban>`
  - Aktia: tab-separated fields with a different field order
  Generate per-vendor in `vendor_to_bank_desc()` and have one
  "messy bank" view that mixes them.
  **(half day; the kind of detail accountants notice in 30 seconds)**

- [ ] **#25 Fraud category in anomalies** — Anomalies clusters
  currently: gl_mismatch / unfamiliar / approver. Real risk
  managers want a "potential fraud" cluster with its own visual
  treatment (red icon, escalation language) even if the demo data
  triggers it via synthetic signals (round-number amount + new
  vendor + amount > €10K). **(half day; lands the risk-manager
  conversation)**

- [ ] **#26 Drift over time** — the cynical old partner's question:
  "what does this look like at 90 days?" The Quality/Rules view
  has a Drifting/Stale status but no time series. Add:
  - Sparkline per rule showing precision over the last 90 days
  - Override count per week, plotted, with annotations on when new
    rule candidates emerged
  - "Stale rules" section that auto-flags rules unused for 30+ days
  **(1-2 days; this is the question that decides repeat sales)**

- [ ] **#27 Multi-entity per customer** — currently 1 customer = 1
  legal entity. Real SaaS customers consolidate multiple entities.
  Add an `entity_id` field; predictions can scope by either
  customer_id or (customer_id, entity_id). **(1 day; common
  enterprise blocker)**

- [ ] **#28 Batch override workflow** — overrides are currently
  shown as historical signal only. Add a "select N invoices, apply
  GL X" batch action on the Invoices page. **(half day)**

- [ ] **#29 Webhook / integration stub** — at minimum, a
  `/api/integrations` page describing how the prediction_log table
  could feed an outbound webhook to NetSuite / Dynamics / Procountor.
  Not a real integration, but a credible architectural sketch.
  **(half day; closes the "can it talk to my ERP" objection)**

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
