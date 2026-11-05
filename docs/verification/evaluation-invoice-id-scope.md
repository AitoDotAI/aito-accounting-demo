# Verification — the linked-invoice evaluation ranks only the tenant's invoices

Branch `fix/evaluation-invoice-id-scope`, split from `fix/evaluation-approver-scope`
(CPO review of #62) because it changes a number the Quality page shows.

**Run on local Aito v2.12.0 (shared's version since 2026-11-05 08:11) with a
15-tenant slice of the demo data, not shared master.** The free image caps a
table at 10,000 rows, so the full dataset cannot load; the slice has 9,875
invoices and 6,176 bank lines. No `_evaluate` was sent to shared.

## What changes

The Payment Matching domain's "Linked invoice" target (`bank_transactions.invoice_id`
-> `invoices.invoice_id`) is evaluated with `invoice_id.customer_id = <tenant>`
in the evaluate `where`, so the candidates are the tenant's own invoices. Before,
`customer_id` in the `where` bounded which payments Aito learned from, not which
invoices it could rank: the candidate set was every tenant's invoices, and
`cases[].predicted` printed whichever it picked.

## Measured: before and after (matching, `description,amount`, limit 10)

| tenant | candidates | accuracy % | meanRank | trainSamples | wall |
|---|---|---|---|---|---|
| CUST-0127 | tenant's invoices (after) | 0.0 | 33.3 | 6166 | 2.5 s |
| CUST-0127 | all tenants (before) | 0.0 | 7418.4 | 6166 | 4.8 s |
| CUST-0001 | tenant's invoices (after) | 0.0 | 4063.5 | 6166 | 4.4 s |
| CUST-0001 | all tenants (before) | 0.0 | 4978.0 | 6166 | 3.9 s |

- `trainSamples` is identical: the linked-row filter does not remove
  null-`invoice_id` (unmatched) payments from training, which settles the open
  question the unit test used to carry.
- Accuracy is 0% either way. Each invoice has exactly one bank line, so a held-out
  line's invoice has no training evidence (perf, td-20261031125252403569). The
  metric cannot pass or fail; no quality claim rests on it.
- **`meanRank` is the shown number that changes** (CUST-0127: 7418 -> 33). It is
  now a rank among the tenant's invoices rather than among all tenants'. This is
  a published-number change and is Antti's to accept before deploy.
- Wall times here are seconds on the slice; on the full dataset the same
  evaluation is minutes (perf), which is why the endpoint's `limit` cap matters.

## Not done

Nothing was run against shared; browser steps not done; the full-dataset numbers
are unmeasured (and should not be measured on shared).
