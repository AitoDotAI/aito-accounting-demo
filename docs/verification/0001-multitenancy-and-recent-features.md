# Verification: Multi-tenancy + master-detail dock + help drawer + evaluation matrix

**Date:** 2026-04-26
**Status:** findings (several major, none blocking the canonical demo path on CUST-0000)

## Scope

- Multi-tenant customer switching (CUST-0000 enterprise / CUST-0040 midmarket /
  CUST-0200 small / CUST-0250 no-precompute / CUST-0254 smallest)
- All nine views: /invoices, /formfill, /matching, /rulemining, /anomalies,
  /quality/overview, /quality/rules, /quality/predictions (Evaluations Matrix),
  /quality/overrides
- Master-detail dock on /invoices (Prediction / Vendor history / Routing trail
  tabs, close, switch row, switch customer with dock open)
- Help drawer (floating "?" button), search, article expand, related articles,
  impressions logging
- Evaluations Matrix (domain switch Invoice / Payment / Help, prediction target
  dropdown, input checkboxes, test-set slider)
- Z-index: customer dropdown vs. prediction-alternatives dropdown
- Bad URLs: empty + nonexistent customer_id, hammer /api/health for 429

## Tooling

Playwright via `frontend/node_modules/playwright-core` driving the chromium
binary at `${PLAYWRIGHT_BROWSERS_PATH}/chromium-1169/chrome-linux/chrome`,
plus `curl` for direct API checks. All scripts and screenshots are under
`/tmp/adversary*.js` and `/tmp/verification-shots/`.

## Scenarios attempted

Every scenario below was actually executed (not just listed):

1. Loaded each of the 9 views on CUST-0000 — all rendered with data, no 5xx.
2. Selected CUST-0040 / CUST-0200 / CUST-0254 via the topbar dropdown
   (open button, type into "Search by id, tier, name…", click the matching
   row), then navigated each of the 9 views client-side via the sidebar Link.
3. Hit each `/api/*` endpoint directly with `curl` for CUST-0000, CUST-0040,
   CUST-0200, CUST-0250, CUST-0254 to compare backend latency vs. UI cache.
4. Counted precomputed JSON files on disk
   (`data/precomputed/CUST-XXXX/*.json`) to see which customers fall back to
   live Aito.
5. Empty / bad customer_id: `/api/invoices/pending?customer_id=` and
   `=NONEXISTENT`.
6. Master-detail dock on /invoices (CUST-0040): clicked the underlined
   invoice ID cell, cycled through Prediction / Vendor history / Routing
   trail tabs, clicked a different invoice to verify dock content refresh,
   closed via the ✕ button, switched customer with dock open.
7. Help drawer: clicked the floating ? bottom-right button, typed "GL code"
   into the drawer search input, waited up to 30s, attempted to click a
   result and look for "Users who read this also read".
8. Evaluations Matrix: opened /quality/predictions, observed the three
   domain tabs (Invoice Processing, Payment Matching, Help Recommendations),
   clicked each, sampled the cases table, looked for a Run / Re-evaluate
   button, counted checkboxes and range sliders.
9. Z-index: opened a `pred-badge ▾` dropdown then opened the customer
   dropdown to see whether the second covers / collides with the first.
10. Hit `/api/health` 70 times serially with curl, counted 200 vs. 429.

## Failures found

### 1. Major — Help drawer search is blocking and returns empty for the suggested term

`GET /api/help/search?customer_id=CUST-0000&q=GL%20code` returned
`{"articles":[]}` after **37.5 seconds**. Empty query (`q=`) returned
`{"articles":[]}` after **132 seconds**. Query "invoice" returned
`{"articles":[]}` after **190 seconds**.

The drawer is only useful if the user is patient enough to wait 30s+ per
keystroke debounce, and even then "GL code" — the term the verification
script suggests in the demo guide — yields zero results. Severity: major
because the help drawer is a headline feature for the demo and currently
neither responsive nor populated.

Root cause is likely that `src/help_service.search_help()` issues a live
Aito `_predict` per request with no cache and no precomputed shortcut
(see `src/app.py:708`).

### 2. Major — Help drawer impressions never fire in this build

Across multiple full interactions with the drawer (open → search → wait →
click visible items) zero `POST /api/help/impression` calls were observed
in the network trace. Either:

- impressions only fire after at least one article renders (and none ever
  do because of finding #1), or
- the impression hook is wired only on click and the article list never
  populates with anything clickable.

Either way, the "every shown article is an impression" claim in the demo
copy is currently aspirational under live Aito timing. Severity: major
because it undermines the recommendation-loop story the demo tells.

### 3. Major — Live (non-precomputed) customers are unusable; only 21 of 255 customers have JSON

Disk inspection (`find data/precomputed -maxdepth 2 -name '*.json' …`)
shows JSON only for CUST-0000 through CUST-0020. The remaining 234
customers fall back to live Aito. Measured first-load latency:

| Customer  | /api/invoices/pending | precomputed? |
|-----------|------------------------|--------------|
| CUST-0000 | 0.006s                 | yes          |
| CUST-0040 | 34.0s                  | no           |
| CUST-0200 | 47.4s                  | no           |
| CUST-0250 | 54.2s                  | no           |
| CUST-0254 | 37.5s                  | no           |

The dropdown lets a developer-evaluator pick any of 255 customers and
silently puts them on a 30–55-second loading path. The CLAUDE.md
"diagnose, don't stack workarounds" prime directive applies here:
either narrow the dropdown to precomputed customers, mark the rest as
"slow — live Aito", or finish the bulk precompute (task #14 is
in-progress). Severity: major for demo credibility, not blocking
CUST-0000 path.

### 4. Major — Evaluations Matrix on Payment Matching / Help Recommendations stalls or empties

After clicking the "Payment Matching" tab the page header shows
"Running _evaluate…" indefinitely, and the cases table is "First 0 of 0
— green=correct, red=wrong" with the message "No cases returned. Pick
at least one input field." However the input-field checkboxes section
is completely absent in the rendered state captured at +20s
(see `/tmp/verification-shots/EVAL-2-payment.png`). Same reproduces on
"Help Recommendations" (`EVAL-3-help.png`).

There is no visible Run button — the evaluation auto-runs whenever
domain / predict / inputs change. So a user who clicks Payment Matching
and waits the better part of a minute sees only "Running…" with no
hint about how to recover. Severity: major because two of three
demoed domains land on a stalled page.

The Invoice Processing default does work: 97% accuracy, top-3 0.789,
+52pp uplift, 50 of 100 cases visible (all green) — a good demo state.

### 5. Major — Bad / empty customer_id returns 200 instead of 4xx

`GET /api/invoices/pending?customer_id=` → 200 with empty result body
in 5.95s.
`GET /api/invoices/pending?customer_id=NONEXISTENT` → 200 with empty
result body in 10.12s.

Per CLAUDE.md ("Never silently filter, coerce, or discard unexpected
data. Assert and fail loudly."), an unknown / empty customer should
yield a 400 with a diagnostic message, not a slow 200 with `[]`.
Currently a frontend bug that drops the customer_id will silently
display "no invoices" instead of a real error, and a third-party
integrator hitting the API will get a misleading green status.
Severity: major because it directly violates a stated invariant.

### 6. Minor — Eval matrix has no visible "Run / Re-run" affordance

Domain / target / inputs auto-trigger `_evaluate` on every change. For
demo purposes that's fine when results appear in 1–2s; under live
Aito (Payment, Help) the user has no way to retry, cancel, or know
what triggered the long call. A persistent "Last run: <timestamp> ·
Re-run" button would help.

### 7. Minor — Customer dropdown has 255 items with no visible pagination or grouping for non-enterprise tiers

The dropdown groups by tier (enterprise / large / midmarket / small)
which is good, but in the small group there are 191 items in one
scroll list. Combined with finding #3 (most are slow) the UX is "pick
something and find out". Suggestion: visually mark the 21 precomputed
customers (e.g. green dot beside row, matching the existing topbar
warm/cold indicator).

### 8. Minor — Help button placement assumes the right rail is always 268px wide

`HelpDrawer.tsx` hard-codes
`right: calc(268px + 24px)` and `right: 268` for the panel — anchored
to the AitoPanel width. Verified visually — works on 1440-wide
viewport. On narrower viewports or when the right panel is hidden the
button would float over empty space; not directly testable in this
session.

## What works (positive findings)

- Multi-tenancy at the API level: each precomputed endpoint
  (`/api/invoices/pending`, `/api/anomalies/scan`,
  `/api/matching/pairs`, `/api/quality/overview`, etc.) correctly
  scopes to the requested customer_id when called directly. Verified
  CUST-0040 anomalies returns 5 flags all prefixed `CUST-0040-INV-…`.
- Master-detail dock works: clicking the underlined invoice ID opens
  the dock; tabs Prediction / Vendor history / Routing trail are
  visible and clickable; the close ✕ closes it; clicking another row
  refreshes the dock contents (verified in
  `B-dock-tab-VENDOR_HISTORY.png` showing CUST-0040 vendor history).
- Z-index regression looks fixed: opening the customer dropdown over
  an open prediction-alt dropdown shows the customer dropdown on top,
  and the AitoPanel right rail is not covered (see
  `L-both-open.png`).
- Rate limiting works as advertised: 70 sequential `/api/health`
  calls produced 59 × 200 + 11 × 429 — ~60/min limit confirmed.
- Sidebar Link navigation preserves selected customer across views
  (Customer state lives in `CustomerProvider` at root layout). A
  full-page reload resets it to CUST-0000, but no view in the app
  forces a reload — sidebar uses `next/link`.
- Customer dropdown popup uses `position: fixed` with computed
  coordinates (CustomerSelector.tsx:62) so it correctly escapes
  parent stacking contexts.

## Screenshots

Key shots in `/tmp/verification-shots/`:

- `B-dock-opened.png`, `B-dock-tab-VENDOR_HISTORY.png`,
  `B-dock-tab-ROUTING_TRAIL.png` — dock works on CUST-0040
- `I-anomalies-CUST-0040.png` — anomalies correctly scoped to 0040
- `I-matching-CUST-0040.png` — matching scoped to 0040
- `K-eval-initial.png` — Invoice Processing eval, 97% accuracy
- `K-eval-Payment_Matching.png` — stuck "Running _evaluate…"
- `EVAL-2-payment.png`, `EVAL-3-help.png` — Payment / Help tabs land
  in unhelpful empty state
- `HELP-search-glcode.png` — help drawer open, "GL code" typed,
  "Loading…" body
- `L-both-open.png` — customer dropdown over prediction-alt dropdown,
  no z-index regression
- `cust_CUST_0040_invoices_.png`, `cust_CUST_0250_invoices_.png` —
  customers without precomputed JSON

## Network observations

| Endpoint | Customer | Time | Status | Notes |
|----------|----------|------|--------|-------|
| /api/health | — | <0.01s | 200 / 429 | rate limit kicks in at 60/min as designed |
| /api/customers | — | 0.01s | 200 | 255 customers returned |
| /api/invoices/pending | CUST-0000 | 0.006s | 200 | precomputed |
| /api/invoices/pending | CUST-0040 | 34.0s | 200 | live Aito |
| /api/invoices/pending | CUST-0200 | 47.4s | 200 | live Aito |
| /api/invoices/pending | CUST-0250 | 54.2s | 200 | live Aito (worst) |
| /api/invoices/pending | CUST-0254 | 37.5s | 200 | live Aito |
| /api/invoices/pending?customer_id= | — | 5.95s | 200 | should be 400 |
| /api/invoices/pending?customer_id=NONEXISTENT | — | 10.12s | 200 | should be 400 |
| /api/anomalies/scan | CUST-0000 | 0.003s | 200 | precomputed (2 flags) |
| /api/anomalies/scan | CUST-0040 | live | 200 | 5 flags scoped correctly |
| /api/matching/pairs | CUST-0000 | 0.003s | 200 | precomputed |
| /api/quality/domains | — | 0.002s | 200 | always fast |
| /api/help/search?q=GL%20code | CUST-0000 | 37.5s | 200 | empty |
| /api/help/search?q= | CUST-0000 | 132s | 200 | empty |
| /api/help/search?q=invoice | CUST-0000 | 190s | 200 | empty |
| /api/help/impression | — | n/a | n/a | never observed in any session |

No 4xx or 5xx unexpected. The "200 with empty body" pattern is the
recurring anti-signal — both for help search and for bad customer_id.

## Recommended fixes, ranked

1. **Validate `customer_id` in API layer** — return 400 for empty /
   unknown values. (CLAUDE.md prime directive #2.)
2. **Precompute help-search responses or cache them server-side** —
   30-second debounce + 30+ second response = unusable.
3. **Finish the bulk precompute (task #14)** or scope the customer
   dropdown to precomputed-only customers in the demo build.
4. **Add a "stuck or empty" state to the Evaluations Matrix Payment /
   Help tabs** — a visible "Re-run" button and "Last run …" timestamp.
5. **Mark cold customers in the dropdown** with the same warm/cold
   indicator already shown for the active customer.
