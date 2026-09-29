# Plan: things that change over time

**Status:** planning note, 2026-09-29. Nothing here is decided. Each item
becomes its own ADR when it is picked up. Ordered by how much it would
strengthen the demo for an accounting audience.

An accounting firm's objection to "the model learned from history" is
always the same: *history changes*. People go on holiday, leave, change
roles; the chart of accounts is revised; a client's business shifts.
Today the demo has no answer, because its data never changes: every
employee is `active: True` (`data/generate_fixtures.py:620`), rules and
approvers are fixed per tenant, and the one time-based view is synthetic
(see Drift).

Aito's relevant property is that it needs no retraining. A change in the
data is visible to the next query. Each item below turns that property into
something a person can watch happen.

## 1. Holidays and delegation

**The case.** Tiina approves software invoices and is away for two weeks.
A predicted approver who is absent is worse than no prediction.

**What exists.** `employees.active` and `employees.supervisor_id` (a link
into `employees`). The fixtures already route ~3% of invoices randomly as
"vacation cover" noise (`generate_fixtures.py:820`), but that noise is not
tied to any absence.

**Direction.**
- Model absence as data: an `absences` table (employee, from, to).
- The app resolves "who approves instead" as a plain rule: the absent
  approver's `supervisor_id`, or their recorded delegate.
- Aito keeps predicting the *usual* approver. The UI shows both: "Usually
  Tiina Kinnunen (away until 12.10) → routes to her supervisor, Matti
  Saarinen."
- This keeps the prediction honest (it is what the history says) and puts
  the calendar fact where it belongs, in a lookup.

**Demo beat.** Mark Tiina away; the next invoice shows the delegation, and
the explanation still says why it would normally be her.

**Open.** Whether delegations recorded as history (approved by the
supervisor while Tiina was away) should also teach Aito that a
supervisor covers. That needs dated fixtures (see 2).

## 2. Person and organisation changes

**The case.** Someone changes department, a new IT manager starts, a
cost centre is merged. The old pattern is still in history, and it is
now wrong.

**What exists.** Nothing time-aware in the invoice data. Rule governance
(ADR 0025) has the right shape: append-only events with a strictly
increasing `valid_from`.

**Direction.**
- Give employees effective-dated role and department history, in the same
  append-only way as `rule_revisions`.
- Predict approvers from recent history. Scope the predict's `where` to
  invoices after the change, or weight recency.
- Which Aito query shape does recency weighting best is not known yet.
  Write it, run it against the data, and add it to the cheatsheet before
  building on it (Prime Directive 3).
- With T2's role-based routing, ADR 0027's linked priors can then say "Kari
  approves this because he is the IT manager (since 1.9.)".

**Demo beat.** Move Tiina to Finance and hire Kari as IT manager. Within
a handful of approved invoices, predictions follow Kari, with no
retraining and no rule edit.

**Open.** How many post-change examples Aito needs before the new
approver outranks the old, on this data. Measure it, don't claim it.

## 3. Chart-of-accounts changes

**The case.** 4400 is split into 4410/4420, or a client migrates to a new
Liikekirjuri-style scheme. Years of history name accounts that no longer
exist.

**What exists.** `GL_LABELS` (with Finnish names since #48), and
overrides that record corrections.

**Direction.**
- Keep an explicit mapping table (old code → new code, effective date).
  Predict in the *old* space where history is deep, and map forward, until
  enough new-code history exists.
- A split (one old code, two new) is a genuine ambiguity. The mapping
  names the candidates, Aito's `$why` on the new-code history picks
  between them as it accumulates, and the UI says which of the two the
  evidence favours.

**Demo beat.** Split one account; show the first invoices routed through
the mapping, then Aito taking over as corrected examples arrive.

**Open.** Whether to rewrite history in Aito (a data migration) or map at
query time. That is a real trade-off for the ADR.

## 4. Drift

**The case.** "What does this look like in 90 days?" A rule that was 98%
right in spring can decay quietly.

**What exists, and a problem.**
- `/api/quality/rules/drift` (app.py:1122) draws per-rule precision
  sparklines over 12 weeks.
- Their history is SYNTHESISED: `quality_service.backfill_rule_drift`
  generates "a stable seeded precision walk". So those sparklines are not
  measurements.
- This is the invented-numbers pattern the 28.9 review flagged. It should
  be labelled or removed now, independent of this plan.
- The view sits under QUALITY, which is developer-only since #48, so it is
  not on the Wednesday path.

**Direction.**
- Measure drift instead of simulating it. Per week, compare what was
  predicted (`prediction_log`) with what was booked (overrides and final
  codes).
- `_evaluate` over time windows gives the same with calibrated metrics.
  Check its cost first: azure's 29.9 log analysis shows `_evaluate` bursts
  push everything else into multi-second tails.
- An alert when a rule's measured precision falls below its promotion
  threshold closes the governance loop from ADR 0025: promote, measure,
  demote.

**Demo beat.** Needs dated fixtures with a real change in them (2 or 3).
Drift is the *consequence* of change, so it comes last.

## Order and dependencies

1. **Now, small:** label or remove the synthetic drift history.
2. **T2 (already planned):** coherent Finnish fixtures that route by role,
   with dated history. Items 1–4 all need dates, and 2 needs roles.
3. **Holidays and delegation (1):** mostly a lookup, the highest demo value
   for the least Aito uncertainty.
4. **Person and org change (2):** one open query-shape question, recency.
5. **Chart-of-accounts change (3):** its ADR hinges on migrate-versus-map.
6. **Measured drift (4):** once the data contains change to measure.
