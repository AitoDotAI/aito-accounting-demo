# Baselines for the v2.11.0 re-check

Captured on **shared.aito.ai 2.10.3** (rev 88786b4d) before v2.11.0, which
fixes predicts on one of two links that point at the same table reading the
other link's projection. Re-run the same queries after the release and
compare. Both surfaces below have two links into one table.

## 1. Approver — `invoices.approver` and `invoices.processor` → `employees`

Scoping a predict on `approver` with `approver.customer_id` should only
remove other tenants' employees, so it can never lower accuracy. On 2.10.3
it does, and it flips answers between two employees of the SAME tenant.

`_evaluate` approver, input `vendor, category, amount_band`, 100 test rows:

| tenant | scope | accuracy | baseAccuracy | meanRank | geomMeanP |
|---|---|---|---|---|---|
| CUST-0000 | none | 0.980 | 0.440 | 0.410 | 0.7469 |
| CUST-0000 | `approver.customer_id` | 0.940 | **0.000** | 0.390 | 0.6875 |
| CUST-0007 | none | 0.970 | 0.620 | 0.050 | 0.7836 |
| CUST-0007 | `approver.customer_id` | 0.850 | **0.000** | 0.160 | 0.6783 |

`_predict` approver on 80 real invoices (CUST-0000 + CUST-0007): unscoped
79/80, scoped 75/80; the top answer came from another tenant 0/80 either way.

**Pass after v2.11.0:** scoped ≥ unscoped, and baseAccuracy > 0. Then
merge `fix/scope-approver-predicts` (Smart Form Fill and the Evaluation
view, currently unscoped) and rebuild the precompute.

## 2. Help "users also read" — `help_impressions.article_id` and `prev_article_id` → `help_articles`

`help_service.related_articles`: `recommend article_id`, goal
`clicked: true`, `basedOn: []`, filtered on the OTHER link
(`prev_article_id.article_id`) and scoped through the target link
(`article_id.customer_id`). Full output for 9 cases — as-is, without the
target scope, without the prev filter — is in `help_related_2.10.3.json`.

Observed on 2.10.3:

- The target scope does real work: without it, up to 5 of the top 5 are
  other tenants' internal articles.
- **CUST-0000 after `CUST-0000-INT-00`** returns APP-00/01/02 at exactly
  `$p = 1.0, 1.0, 1.0`. Saturated, identical probabilities are not a
  ranking; it may be thin data, but it is the case to watch.

**Pass after v2.11.0:** for each case, compare `as_is` top-3 and `$p`. A
changed ranking is not by itself a failure — the fix may correct it — but
every change should be explainable, and no `as_is` result may contain
another tenant's internal article.
