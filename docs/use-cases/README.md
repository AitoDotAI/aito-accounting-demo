# Use case library

One document per major feature, mirroring [aito-demo's
docs/use-cases](https://github.com/AitoDotAI/aito-demo/tree/main/docs/use-cases).
Each page covers: what the feature does, the Aito query that
produces it, how the UI renders the result, performance, and
what's deliberately out of scope.

| # | Feature | Operator | Doc |
|---|---------|----------|-----|
| 1 | Invoice processing | `_predict gl_code`, `_predict approver` | [01-invoice-processing.md](01-invoice-processing.md) |
| 2 | Smart Form Fill | `_predict <field>` per missing field | [02-smart-form-fill.md](02-smart-form-fill.md) |
| 3 | Payment matching | `_predict invoice_id` via schema link | [03-payment-matching.md](03-payment-matching.md) |
| 4 | Rule mining | `_relate` + chained sub-pattern drill | [04-rule-mining.md](04-rule-mining.md) |
| 5 | Anomaly detection | `_predict` in scoring mode | [05-anomaly-detection.md](05-anomaly-detection.md) |
| 6 | Help recommendations | `_recommend WHERE prev_article_id` | [06-help-recommendations.md](06-help-recommendations.md) |
| 7 | Quality dashboard | `_evaluate select: [..., "cases"]` | [07-quality-dashboard.md](07-quality-dashboard.md) |
| 8 | Human overrides | Two-pass `_relate` with link traversal | [08-human-overrides.md](08-human-overrides.md) |
| 9 | Multi-tenancy | `where: {customer_id, ...}` everywhere | [multi-tenant-accounting.md](multi-tenant-accounting.md) |

Every doc links to its implementation in `src/`, the relevant
[ADR](../adr/), and back to the README's quickstart.
