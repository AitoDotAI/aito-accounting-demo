# Demo script — Predictive Ledger (multi-tenant)

> Canonical 5-minute walkthrough.
> Start: `./do dev` then open http://localhost:8200.

## Before you start

1. `./do reset-data` has been run (data in Aito)
2. `./do dev` started — wait ~10s for top-5 customer warmup
   (or run `./do warm-cache --top 20` for a wider warm set)
3. Browser wide enough for **nav + main + Aito side panel**
4. Customer dropdown shows **CUST-0000 · enterprise (2,000)** with
   a **green** "warm" dot

## The headline

> "Same Aito instance, 256 customers, ~250K invoices in one shared
> table. Each customer's predictions scoped by `customer_id` in the
> `where` clause. No model training. No retraining. Add a row,
> predictions update instantly. Watch."

## Walkthrough (5 minutes, in order)

### 1 — Invoice Processing (default landing) [~60 sec]

**What to point out:**

- **Touchless rate** (top-left, gold) — the share of invoices Aito
  routes at ≥ 0.85 confidence. Click it to filter the table to
  touchless rows; click **Review needed** to see the rest.
- **Sorted by due date** with red "Nd overdue" / amber "Due in Nd"
  labels. Accountants live in dates.
- **Source column** — `Rule` (mined per customer, blue),
  `Aito` (predicted, gold), `Review` (amber). Roughly 20–25% of
  invoices match a mined rule; the rest are Aito predictions.
- **Click any GL prediction** — top-3 alternatives appear with
  confidences. Click `?` next to it — `$why` factors show which
  vendor / amount tokens drove the prediction.

**What to say:**

> "These rules aren't hand-coded. The system mined them from this
> customer's history using `_relate`. Notice GL labels are realistic —
> 4400 Materials & Supplies, 5300 Insurance — these come from the
> data, not a hardcoded list."

### 2 — Switch customer to show isolation [~30 sec]

Click the customer dropdown. Search for "small". Pick **CUST-0254**
(16 invoices, small tier).

- The table changes completely — different vendors, different GL
  patterns.
- Touchless rate drops, "Review needed" rises — small customers
  haven't accumulated enough history yet.
- The dot turns amber (cold cache) on first switch, then green.

**What to say:**

> "Same Aito table, same `_predict` operator, just `customer_id`
> changed in the where clause. Aito honestly reports lower confidence
> for the cold-start customer instead of pretending to know."

Switch back to **CUST-0000**.

### 3 — Smart Form Fill [~60 sec]

Click **Smart Form Fill** in nav.

- **Quick-start cards** at the top — recurring vendor templates with
  GL, approver, support count. Click one (e.g. *Investra Management
  Oy → 5300 Insurance*).
- All 7 fields fill in italic gold = "predicted, awaiting confirm".
- Click into one field, type something — instantly **confirmed
  green**, with a check icon. Tab through the rest to confirm them.
- Click `?` next to any prediction — `$why` tooltip shows the input
  features that drove this prediction with their lift values.
- Click **Log submission** in topbar — green banner: "Logged 7 field
  decisions to prediction_log". Real audit table updated in Aito.

**What to say:**

> "Three states: empty / predicted / confirmed. The visual
> distinction matters — predicted-but-wrong silently shipping is the
> worst failure mode in form-fill. Tab confirms; Esc clears. Every
> field decision is logged so you can compute real accuracy from
> historical user behavior, not just self-reported metrics."

### 4 — Toggle "Data flow" [~30 sec]

Click the **Data flow** toggle in the topbar.

- Numbered gold badges appear next to UI elements.
- The Aito side panel shows a **Data flow on this page** section
  listing each numbered step: what the call produces, what the
  query looks like.
- Switch between Form Fill, Invoices, Matching — every page is
  annotated.

**What to say:**

> "Every claim on screen traces back to a specific Aito call. There
> are no hidden ML pipelines. If a number is wrong, you can see
> exactly which query produced it."

### 5 — Payment Matching [~45 sec]

Click **Payment Matching**.

- Two-column layout: open invoices ↔ bank transactions, connected
  by confidence-scored matches.
- The first matched row's **why panel auto-expands** — shows the
  factors Aito used: vendor name token lift, amount proximity.
- Bank descriptions are realistic Finnish: `KESKO HELSINKI / VIITE
  661031599 / PVM 18.08.24` with check-digit-correct Viite numbers.

**What to say:**

> "Aito's `_predict invoice_id` traverses the schema link from
> bank_transactions to invoices in a single query, ranks invoices by
> association with the bank description and amount, and returns the
> full invoice row. No separate matching service, no Levenshtein
> heuristic — it's just `_predict`."

### 6 — Rule Mining + drill-down [~45 sec]

Click **Rule Mining**.

- Each row is a sentence: *"When vendor = 'Investra Management Oy',
  GL is 5300 (Insurance) in 25 of 25 cases — lift 38× over baseline."*
- Click any row → modal opens showing the matching invoices, with
  any disagreeing rows shown first in red.

**What to say:**

> "These are deterministic patterns, not ML. Support ratio is the
> exact historical count from this customer's data. Lift > 5× means
> the pattern is far stronger than random — these are rule
> candidates, ready to promote once support stabilises."

### 7 — Quality / Predictions (close on accuracy) [~45 sec]

Click **Quality** in nav, then **Prediction quality**.

- **Rules-only baseline** card: shows what you'd get with rules alone
  (low coverage, high accuracy within covered).
- **With Aito**: 100% covered, real `_evaluate` accuracy.
- Confidence-vs-accuracy table — derived from `_evaluate`, not made
  up. Use this to pick an auto-approve threshold.

**What to say:**

> "Rules cover the easy 25%. Aito covers the remaining 75% at
> *measured* accuracy from `_evaluate` cross-validation, not
> self-reported metrics. The confidence-vs-accuracy table is what
> a CFO uses to set the auto-approve threshold."

### Optional close — Override Patterns

Click **Quality → Override Patterns**.

- Headline finding callout: *"Reviewers corrected gl_code to 4500 in
  14 recent invoices (lift 38× over baseline). This is a rule
  candidate."*

**What to say:**

> "Every human correction feeds back. `_relate` on the overrides
> table surfaces emerging patterns — these become tomorrow's mined
> rules. The system gets sharper as people use it. Zero retraining
> step."

## Common questions

**"How does Aito handle 1M+ records?"**
Aito's index makes `_predict` O(log n) on the constraint columns.
This demo runs ~250K cleanly; the schema is sized for 1M. The
two-layer cache (in-memory L1 + Aito-table L2) keeps repeat queries
in single-digit milliseconds.

**"What's the training time?"**
Zero. `_predict` queries the index at request time. Add a row, the
next prediction reflects it. No model, no pipeline, no retraining.

**"How is multi-tenancy actually enforced?"**
Every query includes `customer_id` in the `where` clause. Two
customers can use the same vendor and get different predictions
because Aito only looks at rows that match the where filter.
Single-table multi-tenancy — the hardest case to implement, the
most flexible at runtime.

**"Why mine rules at all if Aito predicts everything?"**
Rules are deterministic — predictable, auditable, fast. Aito covers
the long tail. Showing both side-by-side answers the SOX-compliance
question that mostly-ML systems can't.

**"What's the minimum data for cold-start customers?"**
CUST-0254 in this demo has 16 invoices and still produces useful
predictions — but with honest low confidence on novel vendors. The
Quality view shows the cold-start vs warm-customer accuracy
difference directly.
