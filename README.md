# Predictive Ledger

A working demo showing how [Aito.ai](https://aito.ai)'s predictive database
turns accounting software into **predictive** accounting software. Demonstrates
the path from 70% rules-based automation to 90%+ by filling the gap that rules
can't reach — without replacing them.

Part of the Predictive family: Predictive Ledger, Predictive ERP,
Predictive E-Commerce — all powered by the Predictive Database.

## See it in action

Start the backend and open the demo — every view fills with live Aito
predictions:

- **Invoice Processing** — GL code and approver predictions with confidence
  scores, hybrid rules + Aito routing
- **Smart Form Fill** — select a vendor, watch 6 fields predict automatically
- **Rule Mining** — patterns like `category="telecom" → GL 6200 (17/17)`
  discovered via Aito `_relate`
- **Payment Matching** — invoices matched to bank transactions via `_match`
- **Anomaly Detection** — inverse prediction flags unusual invoices
- **Quality Dashboard** — automation rates and override patterns from real data

## Quick start

```bash
# 1. Clone and enter
git clone <repo-url>
cd aito-accounting-demo

# 2. Configure Aito credentials
cp .env.example .env
# Edit .env with your AITO_API_URL and AITO_API_KEY

# 3. Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync

# 4. Load sample data into Aito
./do load-data

# 5. Build the frontend
./do frontend-build

# 6. Start the server
./do dev
# Open http://localhost:8200
```

The Next.js frontend is served from FastAPI on `localhost:8200` — single
port, no CORS issues.

## How it works

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Browser    │────▶│  FastAPI      │────▶│  Aito.ai         │
│  HTML demo  │◀────│  localhost    │◀────│  Predictive DB   │
└─────────────┘     │  :8200       │     │                  │
                    └──────────────┘     └──────────────────┘
```

**Architecture: rules + Aito hybrid**

1. Invoice arrives
2. Rules engine checks known patterns (Telia → GL 6200) — high confidence, instant
3. If no rule matches → Aito `_predict` with vendor, amount, category as context
4. If Aito confidence < 50% → human review queue
5. Human decisions feed back: overrides are mined for new rule candidates via `_relate`

**Aito operators used:**

| Operator | What it does | Used in |
|----------|-------------|---------|
| `_predict` | Predict a field value from context | Invoice Processing, Form Fill, Anomaly Detection |
| `_match` | Find related records across linked tables | Payment Matching |
| `_relate` | Discover statistical patterns | Rule Mining, Override analysis |
| `_search` | Retrieve records | Aggregate metrics |

Key Aito property: **zero training time**. Queries run immediately on ingested
data. No model training step, no pipeline, no waiting. Add a row, predictions
update instantly.

## Project structure

```
├── frontend/                     # Next.js 15 frontend (App Router)
│   ├── app/                      # Pages (invoices, formfill, matching, ...)
│   └── components/               # Shared components (Nav, PredictionBadge, WhyTooltip)
├── src/
│   ├── app.py                    # FastAPI endpoints
│   ├── aito_client.py            # Aito REST API client
│   ├── config.py                 # Environment config (.env loading)
│   ├── invoice_service.py        # Invoice prediction (rules + Aito hybrid)
│   ├── formfill_service.py       # Multi-field prediction from vendor name
│   ├── rulemining_service.py     # Pattern discovery via _relate
│   ├── matching_service.py       # Invoice ↔ bank transaction matching
│   ├── anomaly_service.py        # Inverse prediction anomaly detection
│   ├── quality_service.py        # Aggregate metrics and override analysis
│   └── data_loader.py            # Sample data upload to Aito
├── tests/                        # Test suite (82 tests)
├── data/                         # Sample Finnish accounting dataset
│   ├── invoices.json             # 230 invoices across 17 vendors
│   ├── bank_transactions.json    # 120 bank statement entries
│   └── overrides.json            # 44 human corrections
├── docs/
│   ├── adr/                      # Architecture Decision Records
│   ├── aito-cheatsheet.md        # Verified Aito query patterns
│   └── demo-script.md            # Demo walkthrough guide
├── do                            # Task runner (./do help)
├── pyproject.toml                # Python dependencies (uv)
└── shell.nix                     # Nix development environment
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
| [0007](docs/adr/0007-payment-matching.md) | Payment Matching with `_match` |
| [0008](docs/adr/0008-anomaly-detection.md) | Anomaly Detection — inverse prediction |
| [0009](docs/adr/0009-quality-dashboard.md) | Quality Dashboard — metrics and feedback loop |

## Available commands

```
./do help          Show all commands
./do dev           Start the backend API server (port 8200)
./do demo          Open the HTML demo in a browser
./do load-data     Upload sample data to Aito
./do reset-data    Drop and reload all Aito tables
./do test          Run the test suite (82 tests)
./do check         Run all pre-merge checks
```

## Learn more

- [Aito.ai documentation](https://aito.ai/docs)
- [Aito query cheatsheet](docs/aito-cheatsheet.md) — verified query patterns used in this project
- [Demo walkthrough](docs/demo-script.md) — step-by-step guide
- [Blog: Why Aito predicts accurately with little data](https://aito.ai/blog/why-aito-predicts-accurately-with-little-data/)
