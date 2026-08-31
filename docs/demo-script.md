# Demo script — Predictive Ledger (multi-tenant)

> Canonical 5-minute walkthrough.
> Start: `./do dev` then open http://localhost:8200.

## Before you start

1. `./do reset-data` has been run (data in Aito)
2. `./do precompute` has been run (writes per-customer JSON to
   `data/precomputed/`; views serve from disk in <50 ms)
3. `./do dev` started — server is ready in <1 s when precomputed
   data exists (cache warmup is skipped automatically)
4. Browser wide enough for **nav + main + Aito side panel**
5. Customer dropdown shows **CUST-0000 · enterprise (16,000)** with
   a **green** "warm" dot. Each row in the dropdown shows a
   green/amber dot indicating precomputed vs cold.

## The headline

> "Same Aito instance, 255 customers, 128K invoices in one shared
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

- Each row is a multi-field sentence, and rows come in two kinds (chip
  on the left: **GL code** or **Approver**) — Aito mines a rule set for
  each output an AP clerk codes, from intake inputs only:
  - **GL** — the capitalization rule: *"When vendor = 'Bronex Software
    Oy' AND amount_band = 'large', GL is 1600 (Capital Equipment) in 144
    of 145 — 99%."* A €15k server is an asset; a €200 cable is an
    expense — and Aito found the threshold.
  - **Approver** — the escalation rule: *"When vendor = 'Avarn Security
    Oy' AND amount_band = 'large', approver is Markku Heikkinen in 925
    of 925 — 100%."* The same vendor's smaller invoices route to a
    different signer; large ones escalate to the senior.
- Click any row → modal lists the invoices it fires on, every exception
  first in red, with exact totals that match the headline.

**What to say:**

> "This is the differentiator. Aito mines the multi-field rules a human
> would write — for *every* field they have to code, GL and approver,
> each predicted only from what's known when the invoice arrives. Notice
> it found amount thresholds: large IT purchases capitalize, large
> invoices escalate to a senior approver. Crucially it never uses the
> approver to predict the GL — those are both *outputs*, decided later,
> so a rule that leaned on one couldn't actually fire. Support is the
> exact historical count, auditable in the drill-down — not a model
> estimate. Strong ones are ready to promote."

> Aside for the technical buyer: the `$related` knob caps how many
> candidate fields Aito mines over, so this stays fast even as you add
> input columns — and tenant scoping is a nested `from`, so the numbers
> are this customer's, never the global table's.

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
Aito's index makes `_search` and `_predict` O(log n) on the
constraint columns. Measured on this dataset (128K invoices,
warm connection): `_search` 20 hits ≈ 85 ms, `_predict` ≈ 120 ms,
`_relate` ≈ 80 ms — and the latency is flat across customer tiers
(CUST-0000 with 16K invoices is no slower than CUST-0254 with
125). For the hosted demo we precompute every read view at
build time, so per-customer browser latency is <50 ms.

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
CUST-0254 in this demo has 125 invoices and still produces useful
predictions — but with honest low confidence on novel vendors. In
the precomputed build, small-tier customers (< 1500 invoices)
deliberately ship with empty mined-rules and rule-performance —
the persona is "just signed up, no patterns yet." The Quality
view shows the cold-start vs warm-customer accuracy difference
directly.

---

## Appendix — running this demo on the Aito v2 API

The same walkthrough runs against Aito's **v2 API** (unified `_query`,
collections, and first-class environments) in a branched environment, without
touching the live v1 demo:

```bash
./do v2-build     # build the dataset as v2 collections in env `v2-demo` (idempotent)
./do dev-v2       # serve the demo against v2
```

`./do dev` (no `AITO_V2_ENV`) still runs the v1 path unchanged — no v2 code
executes unless the variable is set. See
[ADR 0017](adr/0017-aito-v2-migration.md).

### What changes in the demo

Steps 1–7 above are **identical on v2** and the numbers are comparable, with
three exceptions worth knowing before you present:

1. **Warm it first.** v2 deliberately bypasses the precomputed bootstrap (that
   JSON is v1-derived, and serving it would hide v2's real numbers), so the
   first load of a heavy view computes live — 15 s for the quality overview up
   to ~4½ min for payment matching. Warm both demo tenants before you start:

   ```bash
   for CID in CUST-0000 CUST-0254; do
     for EP in invoices/pending formfill/templates rules/candidates \
               anomalies/scan quality/overview quality/predictions \
               quality/evaluations quality/audit matching/pairs; do
       curl -s -o /dev/null "http://localhost:8200/api/$EP?customer_id=$CID"
     done
   done
   ```

   After that everything serves in milliseconds and stays warm for an hour.
   Switching to a *third* tenant mid-demo will hit a cold path — don't.

2. **Step 6 (Rule Mining) gets better on v2, and it's worth saying so.** v2
   mines a richer ruleset from the same data — **41 candidates / 34 strong /
   +77.2% coverage**, against v1's 14 / 9 / 44.3%. Same headline rules, plus
   refinements v1 missed (e.g. the Bronex rule tightens from 144/186 to 144/145
   once `amount_band = large` is added to the conjunction).

3. **Step 7 (Quality) — the metrics are comparable again.** This used to carry a
   warning: v2 computed `baseAccuracy` over the whole collection rather than the
   evaluated tenant, inflating the displayed gain, and its `meanRank` was
   1-based where v1's was 0-based. **Both were fixed in core on 2026-08-31**
   (rev `38a234a6`), re-measured on the demo's own 50-row evaluation: v1 `0.44`
   vs v2 `0.4680` baseline, `meanRank` `0.1` on both. The small baseline delta
   is a sampling convention (v1 measures the base rate on the test sample, v2 on
   the training population) — say that if asked, and quote the numbers as they
   stand. Details in [the verification report](verification/aito-v2-ui.md) (D5).

### What is not on v2 yet

**The help drawer (step: Help / "Ask" panel) still runs on v1.** It was blocked
on a core issue — v2's `recommend` silently dropped disjunctive filters on
linked fields, which would have broken the demo's per-tenant article
eligibility. **That was fixed on 2026-08-31** (rev `38a234a6`) and the drawer's
own query now returns correctly-scoped results on v2, so this is ordinary
migration work rather than a blocker; the code just hasn't been switched yet.
Everything else — invoice processing, form fill,
payment matching, anomaly detection, rule mining, and the quality dashboard —
runs on v2.
