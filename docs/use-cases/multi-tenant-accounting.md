# Multi-Tenant Accounting Automation

*Companion to [aito-demo's Invoice Processing](https://github.com/AitoDotAI/aito-demo/blob/main/docs/use-cases/08-invoice-processing.md). This use case extends the same `_predict` pattern to a SaaS context: 255 customers, 128K invoices, single shared Aito instance, per-customer predictions.*

**[Live demo](https://predictive-ledger.aito.ai)** | **[Source code](https://github.com/AitoDotAI/aito-accounting-demo)**

## Overview

This use case demonstrates how Aito.ai handles **single-table multi-tenancy** for an accounting SaaS workload: a single Aito instance serves predictions for hundreds of customer companies, each with their own vendors, GL coding policies, employees, and approval routing — yet the entire mechanism is `customer_id` in the `where` clause.

Where the [grocery-store demo](https://github.com/AitoDotAI/aito-demo) shows 13 ML use cases on a single tenant, this one shows that the **same operators work unchanged at SaaS scale**. No per-tenant model, no training pipeline, no isolation layer beyond a where-clause filter.

## Multi-tenancy in one query

```javascript
// Customer A: Telia bills go to GL 6200 (Telecom), approved by Mikael
await axios.post(`${aitoUrl}/api/v1/_predict`, {
  from: "invoices",
  where: {
    customer_id: "CUST-A",      // <-- the entire isolation mechanism
    vendor: "Telia Finland",
    amount: 890.50,
  },
  predict: "gl_code",
});
// → { feature: "6200", $p: 0.99 }

// Customer B: Telia bills go to GL 4500 (different policy)
await axios.post(`${aitoUrl}/api/v1/_predict`, {
  from: "invoices",
  where: {
    customer_id: "CUST-B",      // same query, different tenant
    vendor: "Telia Finland",
    amount: 890.50,
  },
  predict: "gl_code",
});
// → { feature: "4500", $p: 0.92 }
```

Same instance, same table, same `_predict` operator. Two customers can use the same vendor and get *different* predictions because Aito's index returns probabilities conditional on the matched rows only.

## Dataset shape

The demo runs at a deliberately stressful shape:

| Layer | Records | Notes |
|------|---------|-------|
| `customers` | 255 | Geometric series: 1×16K invoices, 2×8K, 4×4K, ... 128×125 |
| `corporate_entities` | ~1,400 | Real Finnish companies from the [PRH YTJ public registry](https://avoindata.prh.fi/fi/ytj/swagger-ui) |
| `employees` | ~1,200 | Per-customer hierarchies (CEO → Director → Manager → Supervisor → Employee) |
| `invoices` | 128,000 | All carry `customer_id`; vendor pool shared, GL/approver routing per-customer |
| `bank_transactions` | ~68,000 | Linked to invoices for `_predict invoice_id` matching |
| `overrides` | ~7,500 | Human corrections, mined back as new rule candidates |
| `help_articles` | 120 | Per-customer + global product/legal docs ranked by CTR |
| `help_impressions` | ~14,500 | Click stream for `_recommend WHERE prev_article_id` |

The geometric size distribution is deliberate: **the same demo proves Aito works for both ends of the data spectrum.** The 16K-invoice customer shows 99%+ accuracy. The 125-invoice customer still produces useful predictions but with honest low confidence — cold-start handled by Aito's probability scores, not a special code path.

## Five Aito calls power eight views

```
                       ┌────────────────────┐
                       │  customers (255)   │
                       └────────────────────┘
                              │ customer_id
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
 invoices ──────────  bank_transactions  ─── employees
   │     │                    │                      │
   │  [_predict gl_code]      │                      │
   │  [_predict approver]     │                      │
   │     │            [_predict invoice_id]          │
   │     │             via schema link               │
   │     │                                           │
   │  [_relate vendor → gl_code] (rule mining)       │
   │                                                 │
   ▼                                                 ▼
overrides   ──[_relate field=gl_code → corrected_value]──> emerging patterns
   │
[_evaluate] (held-out accuracy for the Quality dashboard)
```

| View | Aito call | What's predicted |
|------|-----------|------------------|
| Invoice Processing | `_predict gl_code`, `_predict approver` | GL code + approver per pending invoice |
| Smart Form Fill | `_predict <each field>` | All 7 form fields from any partial input |
| Payment Matching | `_predict invoice_id` | Bank transaction → invoice via schema link |
| Rule Mining | `_relate condition → gl_code` | Patterns with support, lift, strength |
| Anomaly Detection | `_predict gl_code`, `_predict approver` (low p = flag) | Inverse prediction signals anomalies |
| Quality / Predictions | `_evaluate` | Real accuracy on a held-out test sample |
| Quality / Rules | `_relate` + replay | Mined rules with precision per customer |
| Quality / Overrides | `_relate field=gl_code → corrected_value` | Emerging patterns from human corrections |

## Implementation highlights

### Per-customer rule mining (the killer feature)

Hardcoded rules don't survive multi-tenancy. Each customer has their own GL policy. Solution: mine rules per-customer from `_relate` on each call, cache for 30 minutes:

```python
def mine_rules_for_customer(client, customer_id, top_n=8):
    # Get the customer's most-frequent vendors
    sample = client.search("invoices", {"customer_id": customer_id}, limit=300)
    candidate_vendors = top_vendors(sample, n=20)

    rules = []
    for vendor in candidate_vendors:
        result = client.relate(
            "invoices",
            {"customer_id": customer_id, "vendor": vendor},
            "gl_code",
        )
        top = result["hits"][0]
        f_match = int(top["fs"]["fOnCondition"])
        f_total = int(top["fs"]["fCondition"])
        support_ratio = f_match / f_total

        # Promote to rule only if support is overwhelming
        if f_match >= 5 and support_ratio >= 0.95:
            rules.append({
                "name": f"{vendor} → GL {top['related']['gl_code']['$has']}",
                "vendor": vendor,
                "gl_code": top["related"]["gl_code"]["$has"],
                "approver": most_common_approver(...),
            })
        if len(rules) >= top_n:
            break
    return rules
```

These rules then short-circuit Aito calls for high-support patterns:

```python
def predict_invoice(client, invoice, rules):
    # Check mined rules first — instant, deterministic, auditable
    for rule in rules:
        if rule["vendor"] == invoice["vendor"]:
            return RulePrediction(rule)  # source="rule", confidence=0.99

    # Fall through to Aito for everything else
    return client.predict("invoices", {
        "customer_id": invoice["customer_id"],
        "vendor": invoice["vendor"],
        "amount": invoice["amount"],
        "category": invoice["category"],
    }, "gl_code")
```

This hybrid covers SOX/audit ("show me the deterministic rules") and ML accuracy ("predict everything else") in the same code path.

### Template prediction (one-click form fill)

`predict_template` finds the joint mode of (gl_code, approver, cost_centre) for a vendor's history. When a vendor has 15+ invoices that all routed the same way, the form fills with one click:

```python
def predict_template(client, customer_id, vendor):
    hits = client.search("invoices",
        {"customer_id": customer_id, "vendor": vendor}, limit=50).hits

    # Joint mode of the high-signal classification fields
    counts = Counter(
        (inv["gl_code"], inv["approver"], inv["cost_centre"])
        for inv in hits
    )
    (gl, approver, cc), n = counts.most_common(1)[0]
    confidence = n / len(hits)

    if confidence < 0.20:
        return None  # too noisy to call it a template

    # Resolve secondary fields by mode within the matched template
    matched = [i for i in hits if (i["gl_code"], i["approver"], i["cost_centre"]) == (gl, approver, cc)]
    return {
        "vendor": vendor,
        "match_count": n, "total_history": len(hits), "confidence": confidence,
        "fields": {
            "gl_code": gl, "approver": approver, "cost_centre": cc,
            "vat_pct": mode("vat_pct", matched),
            "payment_method": mode("payment_method", matched),
            ...
        },
    }
```

### Two-layer cache (Aito as cache store)

```
Read:  L1 (in-memory dict)  →  L2 (Aito cache_entries table)  →  compute
                                                                    │
Write: L1 + L2 (best-effort) ◀──────────────────────────────────────┘
```

L1 is microsecond access for repeat hits. L2 survives server restarts — first request after deploy is ~300ms (L2 read) instead of 15s (recompute). And the storytelling lands: same Aito instance serves predictions, schema, *and* the cache.

## Performance at this scale

After warming the top 5 customers (parallel, ~30s on startup), every cached endpoint returns in single-digit milliseconds:

```
/api/invoices/pending            17ms   (paginated, 20 per page)
/api/matching/pairs              3ms    (8 transactions × 1 _predict each)
/api/rules/candidates            4ms    (relate over distinct values)
/api/anomalies/scan              2ms    (15 invoices × 2 _predict each)
/api/quality/overview            3ms    (search aggregates)
```

Cold (non-precomputed) customers: ~15-25s for the first invoices/pending request, then cached. For the hosted demo every customer is precomputed at build time, so the browser-perceived latency is <50 ms regardless of tenant.

## Things this demo proves

1. **Single-table multi-tenancy works at scale.** 128K rows in one `invoices` table, 255 tenants, where-clause isolation, no measurable slowdown across customer sizes (`_search` ~85 ms whether the customer has 16K or 125 invoices).
2. **No per-tenant training.** All 255 customers share the same Aito instance with no setup beyond inserting their data.
3. **Cold-start is honest.** A customer with 125 invoices gets predictions with low confidence, not fake confidence.
4. **Hybrid rules + ML is achievable in one query path.** Mined rules + `_predict` fallback in `predict_invoice()`, ~30 lines.
5. **Real evaluation is one Aito call.** `_evaluate` returns held-out accuracy with rule-baseline comparison, no ML harness needed.
6. **Audit trail is built-in.** `prediction_log` table captures every field decision; `_relate` on overrides surfaces drift; `last_reviewed` columns satisfy SOX questions.

## Schema

```json
{
  "customers": {
    "type": "table",
    "columns": {
      "customer_id": { "type": "String" },
      "name": { "type": "String" },
      "size_tier": { "type": "String" },
      "invoice_count": { "type": "Int" },
      "employee_count": { "type": "Int" }
    }
  },
  "corporate_entities": {
    "type": "table",
    "columns": {
      "business_id": { "type": "String" },
      "name": { "type": "Text", "analyzer": "english" },
      "industry_code": { "type": "String" },
      "industry": { "type": "String" },
      "city": { "type": "String" }
    }
  },
  "employees": {
    "type": "table",
    "columns": {
      "employee_id": { "type": "String" },
      "customer_id": { "type": "String", "link": "customers.customer_id" },
      "name": { "type": "String" },
      "role": { "type": "String" },
      "department": { "type": "String" },
      "supervisor_id": { "type": "String", "link": "employees.employee_id", "nullable": true }
    }
  },
  "invoices": {
    "type": "table",
    "columns": {
      "invoice_id": { "type": "String" },
      "customer_id": { "type": "String", "link": "customers.customer_id" },
      "vendor_business_id": { "type": "String", "link": "corporate_entities.business_id" },
      "vendor": { "type": "String" },
      "amount": { "type": "Decimal" },
      "category": { "type": "String" },
      "gl_code": { "type": "String" },
      "approver": { "type": "String" },
      "processor": { "type": "String", "link": "employees.employee_id" },
      "vat_pct": { "type": "Int" },
      "payment_method": { "type": "String" },
      "due_days": { "type": "Int" },
      "description": { "type": "Text", "analyzer": "english" },
      "invoice_date": { "type": "String" },
      "routed": { "type": "Boolean" },
      "routed_by": { "type": "String" }
    }
  },
  "bank_transactions": {
    "type": "table",
    "columns": {
      "transaction_id": { "type": "String" },
      "customer_id": { "type": "String", "link": "customers.customer_id" },
      "description": { "type": "Text", "analyzer": "english" },
      "amount": { "type": "Decimal" },
      "invoice_id": { "type": "String", "link": "invoices.invoice_id", "nullable": true }
    }
  },
  "overrides": {
    "type": "table",
    "columns": {
      "override_id": { "type": "String" },
      "customer_id": { "type": "String", "link": "customers.customer_id" },
      "invoice_id": { "type": "String", "link": "invoices.invoice_id" },
      "field": { "type": "String" },
      "predicted_value": { "type": "String" },
      "corrected_value": { "type": "String" },
      "confidence_was": { "type": "Decimal" },
      "corrected_by": { "type": "String" }
    }
  }
}
```

## When to use this pattern

This use case is the right reference when:

- You're building a multi-tenant SaaS where each customer has its own data, but you want one ML system serving all of them.
- You need predictions to vary by tenant (different policies, different vendor sets, different routing rules).
- You can't accept retraining downtime — adding a customer should be the same as inserting a row.
- Audit / SOX compliance requires both deterministic rules *and* ML predictions traceable to specific queries.
- Cold-start customers must coexist with rich-data customers without separate code paths.

If you're a single-tenant app, the simpler [aito-demo grocery-store reference](https://github.com/AitoDotAI/aito-demo) is a better starting point.

## Related references

- **[aito-demo grocery-store](https://github.com/AitoDotAI/aito-demo)** — 13 single-tenant use cases (recommend, autocomplete, search, etc.)
- **[Aito.ai docs](https://aito.ai/docs)** — `_predict`, `_relate`, `_evaluate`, schema linking
- **[PRH YTJ API](https://avoindata.prh.fi/fi/ytj/swagger-ui)** — Finnish company registry, source of corporate_entities
- **[Why Aito predicts accurately with little data](https://aito.ai/blog/why-aito-predicts-accurately-with-little-data/)** — the underlying theory; relevant for cold-start customers
