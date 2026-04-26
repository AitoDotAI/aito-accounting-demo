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

- [ ] **#1 Mine rules from data** — replace synthetic `RULES` array with
  top-N high-precision `_relate` patterns per customer. Quality/Rules
  currently empty because hardcoded rules are for old vendors.

## Todo (priority order)

### Big wins

- [ ] **#3 Searchable customer picker** — 256 customers in a dropdown
  is unusable. Group by tier, add search.
- [ ] **#5 Touchless drill-down** — click "97% touchless rate" on
  Invoices to filter to the 3% review-needed, with reasons.
- [ ] **#2 Template-first Form Fill** — show "Recently used templates"
  list before any input; users start from a template, not blank.
- [ ] **#4 Data-flow tour** — toggle on each page that overlays which
  Aito calls produce which UI elements. Builds evaluator trust.

### Polish

- [ ] **#6 Cold-start onboarding indicator** for small customers
- [ ] **#7 Date handling**: rolling-window dates so demo never goes stale
- [ ] **#8 Progressive skeletons** — render structure first, fill predictions in
- [ ] **#9 Form Fill banner**: collapse after first display
- [ ] **#10 Anomaly recommendation buttons** — make them do something

### Architecture / hygiene

- [ ] **#11 Remove stale single-tenant RULES + KNOWN_VENDORS**
- [ ] **#12 Aito client retry / circuit breaker**
- [ ] **#13 Two-layer cache write race** — per-key lock around compute+set
- [ ] **#14 Booktest coverage**: drill-down, template, formfill-submit,
  prediction_log endpoints
- [ ] **#15 Update README and demo-script.md** for multi-tenant flow

### Story / messaging (towards public release)

- [ ] **#16 Above-the-fold framing**: 1-line on landing page explaining
  what this is and why it's interesting
- [ ] **#17 Provable "no training"**: link to read-only Aito console for
  schema + run-your-own-query
- [ ] **#18 Lift number tooltip**: explain "lift 38× = 38× more often
  than random; >5× is strong"
- [ ] **Use-case page** in aito-demo style: a markdown file at
  `docs/use-cases/accounting-multitenant.md` matching the existing
  numbered-use-case format, ready to drop into the public library

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

### Foundation (earlier)
- [x] 100K invoices, pre-computed predictions architecture
- [x] Multi-tenancy: 256 customers, 1M-capable schema
- [x] Real Finnish company data from PRH YTJ API
- [x] Two-layer cache (in-memory L1 + Aito L2)
- [x] 14 booktests (data sanity, predict, relate, match, evaluate)
- [x] Workflow scripts: fetch-companies, generate-data, load-data,
      precompute, warm-cache
