# Predictive Ledger — Multi-tenant accounting on Aito.ai

A working reference implementation showing how [Aito.ai](https://aito.ai)
turns accounting software into **predictive** accounting software in a
**multi-tenant SaaS** setting: 256 customers, ~250K invoices, all sharing
a single Aito instance — each customer's predictions scoped by
`customer_id` in the `where` clause.

Companion to [aito-demo](https://github.com/AitoDotAI/aito-demo) (the
e-commerce reference). Where that one shows recommend / autocomplete /
product analytics on a grocery store, this one shows GL coding,
approver routing, payment matching, anomaly detection, and rule mining
on a Finnish AP automation workload.

> **No model training.** No pipeline. No retraining. Add a row, predictions
> update instantly. Same Aito instance, same `_predict` operator, scoped
> per customer.

## See it in action

| View | What it does | Key Aito call |
|------|--------------|---------------|
| **Invoice Processing** | GL code + approver predictions, sorted by due date, with VAT and confidence | `_predict gl_code WHERE customer_id, vendor, amount, category` |
| **Smart Form Fill** | Quick-start templates for recurring vendors; multi-field prediction with $why | `_predict <field>` + `predict_template` joint mode |
| **Payment Matching** | Bank transactions matched to invoices via the `invoice_id` schema link | `_predict invoice_id WHERE customer_id, description, amount` |
| **Rule Mining** | Per-customer patterns ("when vendor=X, GL is Y in 4123/4156 cases, lift 38×") | `_relate WHERE customer_id, vendor → gl_code` |
| **Anomaly Detection** | Inverse prediction: low confidence on predictable fields = anomaly signal, clustered by reason | `_predict gl_code` (low p = flag) |
| **Quality / Predictions** | Real `_evaluate` accuracy on held-out data, vs rules-only baseline | `_evaluate` |
| **Quality / Rules** | Mined rules with precision, owner, last-reviewed columns | `_relate` + replay on sample |
| **Quality / Overrides** | Override patterns surfaced via `_relate` on the overrides table | `_relate WHERE field=gl_code → corrected_value` |

A "Data flow" toggle in the topbar overlays numbered badges showing
which Aito call produced which UI element — every claim is traceable
to a query.

## Quick start

```bash
# 1. Clone
git clone <repo-url>
cd aito-accounting-demo

# 2. Configure Aito credentials
cp .env.example .env
# Edit .env with your AITO_API_URL and AITO_API_KEY

# 3. Install dependencies (uv: https://docs.astral.sh/uv/)
uv sync

# 4. Fetch ~1400 real Finnish companies from PRH (one-time, ~2 min)
./do fetch-companies

# 5. Generate fixtures (default ~250K invoices; --small for quick dev)
./do generate-data --small

# 6. Upload to Aito (creates tables, batches inserts, optimizes)
./do reset-data

# 7. (Optional) Pre-compute every read-only view's JSON. Recommended
#    for hosted demos -- views load in <20 ms instead of calling Aito.
#    Skip this in dev; the API falls back to live Aito calls.
./do precompute --workers 4

# 8. Build the frontend and start the server
./do frontend-build
./do dev
# Open http://localhost:8200
```

The Next.js frontend is served from FastAPI on `localhost:8200` —
single port, no CORS issues.

**Performance modes**:
- **With precomputed JSON** (`./do precompute` was run): all read views
  serve from `data/precomputed/{customer_id}/*.json` in <20 ms. Only
  Form Fill calls Aito at runtime.
- **Without precomputed JSON**: read endpoints hit Aito live, with
  L1 (in-memory) + L2 (`cache_entries` table) caching. First request
  per customer takes ~15 s; cached for 5 min after.

For deployments, see [`docs/deploy-azure.md`](docs/deploy-azure.md) —
one-shot `./do azure-deploy` after a one-time Container Apps setup.

## Multi-tenancy at a glance

```
┌─ customers (256 rows) ──────────────────────────────┐
│  CUST-0000  enterprise   2000 invoices              │
│  CUST-0001  enterprise   1000 invoices              │
│  ...        large/midmarket/small tiers             │
│  CUST-0254  small          16 invoices  ← cold start│
└─────────────────────────────────────────────────────┘
                       │
                       │ customer_id
                       ▼
┌─ invoices (~250K) ──── employees ──── corporate_entities ─┐
│   bank_transactions (~150K)    overrides (~15K)           │
│   prediction_log (audit)       cache_entries (L2 cache)   │
└──────────────────────────────────────────────────────────-┘
```

All tables carry `customer_id`. Every `_predict`, `_relate`, and
`_search` call adds `customer_id` to the `where` clause:

```python
client.predict("invoices",
    {"customer_id": "CUST-0000", "vendor": "Telia Finland", "amount": 890},
    "gl_code")
```

Same vendor + same amount, different customers → different predictions.
That's the entire multi-tenancy mechanism.

### Geometric size distribution

The 256 customers are distributed in a geometric series so the demo
covers both ends of the data spectrum at once:

| Tier | Customers | Invoices each |
|------|-----------|---------------|
| Enterprise | 1 | 128,000 |
| Enterprise | 2 | 64,000 |
| Large | 4 | 32,000 |
| Large | 8 | 16,000 |
| Midmarket | 16 | 8,000 |
| Midmarket | 32 | 4,000 |
| Small | 64 | 2,000 |
| Small | 128 | 1,000 |

This proves Aito works at both ends: top customer with rich history
shows 99%+ accuracy; bottom customer with 1K invoices still produces
useful predictions but with honest uncertainty (cold-start mode).

## How predictions work

```
                  Invoice arrives (vendor, amount, ...)
                              │
                              ▼
         ┌────────────────────────────────────────┐
         │  Mined rules (per customer)            │  ← _relate, support ≥ 0.95
         │  e.g. "Telia Finland → GL 6200"        │
         └────────────────────────────────────────┘
                              │
                  match? ─────┼───── no match
                  │                       │
                  ▼                       ▼
        source: "rule"          ┌────────────────────┐
        confidence: 0.99        │ Aito _predict      │
                                │ gl_code, approver  │
                                └────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                       p ≥ 0.85                  p < 0.85
                       source: "aito"            source: "review"
                       auto-route               human queue
                                                          │
                                                          ▼
                                              human override → overrides table
                                                          │
                                                          ▼
                                              _relate mines new rule candidates
                                                          │
                                                          ▼
                                              Loop closes — system learns
```

**Rules are mined, not hand-coded.** The `mine_rules_for_customer()`
function calls `_relate(vendor → gl_code)` per customer and returns
patterns where support_ratio ≥ 0.95 with at least 5 matches. A
Telia → 6200 rule for one customer might be Telia → 4500 for another.

**Aito operators used:**

| Operator | What it does | Used in |
|----------|-------------|---------|
| `_predict` | Predict a field value from context | Invoice Processing, Form Fill, Anomaly Detection, Matching |
| `_relate` | Discover statistical patterns with support and lift | Rule Mining, Override analysis, mined rules per customer |
| `_evaluate` | Cross-validation accuracy on a held-out sample | Quality / Predictions |
| `_search` | Retrieve records | Aggregate metrics, customer/vendor lookup |

## Project structure

```
├── frontend/                     # Next.js 15 (App Router, static export)
│   ├── app/                      # 9 views: invoices, formfill, matching,
│   │                             #   rulemining, anomalies, quality/{4}
│   ├── components/shell/         # Nav, TopBar, AitoPanel, CustomerSelector
│   ├── components/prediction/    # SmartField (3-state), PredictionBadge, WhyTooltip
│   └── lib/                      # customer-context, tour-context, demo-time
├── src/
│   ├── app.py                    # FastAPI endpoints (all customer-scoped)
│   ├── aito_client.py            # Aito REST client
│   ├── invoice_service.py        # Predict GL + approver; rules optional arg
│   ├── formfill_service.py       # Multi-field predict + predict_template()
│   ├── rulemining_service.py     # Pattern discovery via _relate
│   ├── matching_service.py       # _predict invoice_id via schema link
│   ├── anomaly_service.py        # Inverse prediction, clustered by reason
│   ├── quality_service.py        # mine_rules_for_customer, _evaluate
│   ├── cache.py                  # 2-layer cache: dict L1 + Aito-table L2
│   ├── date_window.py            # Frozen demo "today" (2026-04-30)
│   └── data_loader.py            # Schema + batch upload + optimize
├── tests/                        # 81 unit tests (pytest, httpx mocks)
├── book/                         # 14 booktest snapshots — live Aito sanity
├── data/
│   ├── fetch_companies.py        # PRH YTJ API → corporate_entities
│   ├── generate_fixtures.py      # 256 customers, geometric series, FI patterns
│   └── (gitignored) invoices.json, customers.json, ...
├── scripts/
│   └── warm_cache.py             # Pre-warm top-N customer caches
├── docs/
│   ├── BACKLOG.md                # Live kanban (Active / Todo / Done)
│   ├── adr/                      # Architecture Decision Records
│   ├── aito-cheatsheet.md        # Verified Aito query patterns
│   └── demo-script.md            # 5-minute walkthrough
├── do                            # Task runner (./do help)
└── pyproject.toml                # Python deps (uv)
```

## Available commands

```
Data pipeline
  ./do fetch-companies     Download Finnish companies from PRH YTJ API
  ./do generate-data       Generate fixture data (--small / --medium / default 1M)
  ./do load-data           Upload fixture data to Aito (and optimize tables)
  ./do reset-data          Drop all tables and reload from fixtures
  ./do optimize            Optimize Aito tables for faster queries
  ./do warm-cache          Pre-warm API cache for top customers

Development
  ./do dev                 Start the backend API server (port 8200)
  ./do frontend-dev        Start Next.js dev server (port 3000)
  ./do frontend-build      Build Next.js static export
  ./do demo                Open the demo in browser

Testing
  ./do test                Run unit tests (pytest, 81 tests)
  ./do book                Run book tests (snapshot tests against live Aito)
  ./do book-update         Update book test snapshots
  ./do book-capture        Capture fresh snapshots from live Aito
```

## Architecture Decision Records

| ADR | Decision |
|-----|----------|
| [0001](docs/adr/0001-project-foundation.md) | Project scaffold, tooling, initial demo |
| [0002](docs/adr/0002-python-backend-aito-client.md) | Python backend with Aito client library |
| [0003](docs/adr/0003-sample-dataset-loader.md) | Sample dataset and data loader |
| [0004](docs/adr/0004-invoice-processing-live.md) | Invoice Processing with live predictions |
| [0005](docs/adr/0005-smart-form-fill.md) | Smart Form Fill — multi-field prediction |
| [0006](docs/adr/0006-rule-mining.md) | Rule Mining with `_relate` |
| [0007](docs/adr/0007-payment-matching.md) | Payment Matching with `_predict invoice_id` |
| [0008](docs/adr/0008-anomaly-detection.md) | Anomaly Detection — inverse prediction |
| [0009](docs/adr/0009-quality-dashboard.md) | Quality Dashboard — metrics and feedback loop |

## Learn more

- [Aito.ai documentation](https://aito.ai/docs)
- [Aito query cheatsheet](docs/aito-cheatsheet.md) — verified query patterns used in this project
- [Demo walkthrough](docs/demo-script.md) — step-by-step guide
- [aito-demo](https://github.com/AitoDotAI/aito-demo) — the companion e-commerce reference
- [PRH YTJ API](https://avoindata.prh.fi/fi/ytj/swagger-ui) — Finnish company registry, source of vendor data
