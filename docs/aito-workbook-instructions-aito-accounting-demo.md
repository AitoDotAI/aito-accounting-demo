# Aito Workbook Creation Instructions

This document contains instructions for creating workbooks for the Aito instance "aito-accounting-demo".

## Setup

The workbook API is accessed through the Aito Console, not the Aito instance directly.

**Console URLs:**
- Production: `https://console.aito.ai`
- Local development: `http://localhost:3000`

**Authentication:** Use the same `x-api-key` header you used to fetch these instructions.
All workbook API endpoints are under `/api/workbooks/api-key/...` — no session cookie needed.

**Environment variables for your requests:**

```bash
# Console URL (where the workbook API lives)
AITO_CONSOLE_URL=https://console.aito.ai  # or http://localhost:3000 for local dev

# Instance information
AITO_INSTANCE_URL=https://shared.aito.ai/db/aito-accounting-demo
AITO_INSTANCE_ID=68a0e2b0-e34d-4e42-86e4-282555377a7a

# Use the same API key you used to fetch these instructions
AITO_API_KEY=<your x-api-key value>
```

## Instance Information

- **Name**: aito-accounting-demo
- **URL**: https://shared.aito.ai/db/aito-accounting-demo
- **Instance ID**: 68a0e2b0-e34d-4e42-86e4-282555377a7a

## Database Schema

### Table: invoices

| Column | Type | Description |
|--------|------|-------------|
| amount | Decimal | |
| approver | String | |
| category | String | |
| cost_centre | String | |
| description | Text | |
| due_days | Int | |
| gl_code | String | |
| invoice_id | String | |
| payment_method | String | |
| routed | Boolean | |
| routed_by | String | |
| vat_pct | Int | |
| vendor | String | |
| vendor_country | String | |

### Table: bank_transactions

| Column | Type | Description |
|--------|------|-------------|
| amount | Decimal | |
| bank | String | |
| description | Text | |
| invoice_id | String | |
| transaction_id | String | |
| vendor_name | Text | |

### Table: overrides

| Column | Type | Description |
|--------|------|-------------|
| confidence_was | Decimal | |
| corrected_by | String | |
| corrected_value | String | |
| field | String | |
| invoice_id | String | |
| override_id | String | |
| predicted_value | String | |

### Table: prediction_cache

| Column | Type | Description |
|--------|------|-------------|
| cache_key | String | |
| created_at | String | |
| endpoint | String | |
| response_json | String | |

## Aito Query Language

### Query Endpoints

Aito provides several query endpoints for different use cases:

#### /_query
Basic data query with filtering, aggregation, and ordering.

```json
{
  "from": "table_name",
  "where": { "column": "value" },
  "limit": 10
}
```

#### /_predict
Predict the value of an unknown column based on known values.

**Use case**: Classification, regression, filling missing values

```json
{
  "from": "customers",
  "where": {
    "age": 35,
    "plan_type": "basic"
  },
  "predict": "churned"
}
```

#### /_recommend
Find the best matching rows given partial information.

**Use case**: Product recommendations, content suggestions

```json
{
  "from": "products",
  "where": {
    "category": "electronics"
  },
  "recommend": "name",
  "limit": 5
}
```

#### /_match
Find rows matching criteria with relevance scoring.

**Use case**: Search, finding similar items

```json
{
  "from": "customers",
  "match": {
    "industry": "technology",
    "company_size": "medium"
  },
  "limit": 10
}
```

#### /_similarity
Find rows similar to a given row.

**Use case**: "More like this", duplicate detection

#### /_relate
Discover statistical relationships between columns.

**Use case**: Data exploration, feature importance

```json
{
  "from": "orders",
  "relate": ["product_category", "customer_segment"]
}
```

#### /_evaluate
Test prediction accuracy using cross-validation.

**Use case**: Model validation, accuracy metrics

#### /_aggregate
Aggregate data with grouping and statistics.

**Use case**: Summarizing data, counting groups, computing averages

Aggregation functions: `$f` (frequency/count), `$sum`, `$mean`
Format: `"fieldName.$function"`

```json
{
  "from": "orders",
  "aggregate": ["product_category.$f"]
}
```

Multiple aggregations:
```json
{
  "from": "orders",
  "where": { "status": "completed" },
  "aggregate": ["amount.$sum", "amount.$mean"]
}
```

## Workbook Format

### Workbook Structure

A workbook consists of sections, which contain widgets.

```json
{
  "name": "My Workbook",
  "description": "Optional description",
  "sections": [
    {
      "title": "Section Title",
      "description": "Optional section description",
      "widgets": [
        { "type": "text", "title": "Welcome", "config": {...} },
        { "type": "query", "title": "Example Query", "config": {...} }
      ]
    }
  ]
}
```

### Widget Types

#### text
Static text/markdown content for explanations.

```json
{
  "type": "text",
  "title": "Introduction",
  "size": "full",
  "config": {
    "content": "# Welcome\n\nThis workbook demonstrates..."
  }
}
```

#### query
Interactive query widget to run Aito queries.

```json
{
  "type": "query",
  "title": "List Products",
  "size": "full",
  "config": {
    "query": { "from": "products", "limit": 10 },
    "endpoint": "query",
    "displayMode": "playground",
    "outputFormat": "table",
    "runPolicy": "manual"
  }
}
```

**Config options:**
- `query`: The Aito query object
- `endpoint`: "query", "predict", "recommend", "match", "similarity", "relate", "evaluate", "aggregate"
- `displayMode`: "playground" (editable) or "fixed" (read-only)
- `outputFormat`: "table", "json", "kpi", "chart"
- `runPolicy`: "manual", "onLoad"
- `hideQuery`: true to hide the query editor

#### evaluate
Test prediction accuracy with cross-validation.

```json
{
  "type": "evaluate",
  "title": "Prediction Accuracy",
  "size": "full",
  "config": {
    "queryType": "predict",
    "query": {
      "from": "customers",
      "predict": "churned",
      "where": { "age": { "$get": "age" } }
    },
    "testSelection": { "type": "random", "percentage": 20 }
  }
}
```

#### form
Interactive form to collect user input.

```json
{
  "type": "form",
  "title": "Customer Input",
  "size": "medium",
  "config": {
    "fields": [
      { "name": "age", "label": "Age", "type": "number" },
      { "name": "plan", "label": "Plan", "type": "select", "options": [...] }
    ],
    "layout": "vertical"
  }
}
```

#### metrics
Real-time activity metrics for the instance.

```json
{
  "type": "metrics",
  "title": "Instance Activity",
  "size": "full",
  "config": {
    "displayFields": ["status", "lastRequest", "requests5min", "requests1hr", "memory", "disk"],
    "refreshIntervalSeconds": 30
  }
}
```

**Config options:**
- `displayFields`: Array of fields to display: "status", "lastRequest", "requests5min", "requests1hr", "memory", "disk"
- `refreshIntervalSeconds`: Auto-refresh interval (default: 30)

#### image
Display an image from a URL with optional caption.

```json
{
  "type": "image",
  "title": "Architecture Diagram",
  "size": "full",
  "config": {
    "url": "https://example.com/diagram.png",
    "alt": "System architecture diagram",
    "caption": "Figure 1: High-level system architecture"
  }
}
```

**Config options:**
- `url`: Image URL (required)
- `alt`: Alt text for accessibility
- `caption`: Caption text displayed below the image

### Widget Sizes

- `small`: 25% width
- `medium`: 50% width
- `large`: 75% width
- `full`: 100% width (default)

## Creating Workbooks via API

### Using API Key (Recommended for CLI tools)

Create a workbook using your read-write API key:

```bash
curl -X POST "${AITO_CONSOLE_URL}/api/workbooks/api-key/workbooks/from-definition" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${AITO_API_KEY}" \
  -d @workbook.json
```

List existing workbooks:

```bash
curl "${AITO_CONSOLE_URL}/api/workbooks/api-key/workbooks" \
  -H "x-api-key: ${AITO_API_KEY}"
```

Get a specific workbook:

```bash
curl "${AITO_CONSOLE_URL}/api/workbooks/api-key/workbooks/{workbookId}" \
  -H "x-api-key: ${AITO_API_KEY}"
```

Update a workbook:

```bash
curl -X PUT "${AITO_CONSOLE_URL}/api/workbooks/api-key/workbooks/{workbookId}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${AITO_API_KEY}" \
  -d '{"name": "Updated Name", "description": "Updated description"}'
```

Delete a workbook:

```bash
curl -X DELETE "${AITO_CONSOLE_URL}/api/workbooks/api-key/workbooks/{workbookId}" \
  -H "x-api-key: ${AITO_API_KEY}"
```

### Query Data from Aito Instance

To test queries against the Aito database:

```bash
curl -X POST "https://shared.aito.ai/db/aito-accounting-demo/api/v1/_query" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${AITO_API_KEY}" \
  -d '{"from": "table_name", "limit": 5}'
```

## Example Workbook

```json
{
  "name": "Example Workbook",
  "description": "A sample workbook demonstrating different widget types",
  "sections": [
    {
      "title": "Introduction",
      "widgets": [
        {
          "type": "text",
          "title": "Welcome",
          "size": "full",
          "config": {
            "content": "# Welcome to Your Workbook\n\nThis workbook helps you explore and analyze your data.\n\n**Getting Started:**\n1. Run the example query below\n2. Modify the query to explore your data\n3. Add new widgets as needed"
          }
        }
      ]
    },
    {
      "title": "Data Exploration",
      "widgets": [
        {
          "type": "query",
          "title": "Browse invoices",
          "size": "full",
          "config": {
            "query": {
              "from": "invoices",
              "limit": 10
            },
            "endpoint": "query",
            "displayMode": "playground",
            "outputFormat": "table",
            "runPolicy": "manual"
          }
        }
      ]
    }
  ]
}
```

## Tips for Good Workbooks

1. Start with a **text widget** explaining the workbook's purpose
2. Use **query widgets** with `displayMode: "playground"` for interactive exploration
3. Use **query widgets** with `displayMode: "fixed"` and `hideQuery: true` for clean dashboards
4. Group related widgets in sections
5. Use descriptive titles that explain what each widget does
6. Consider the user's workflow - what questions will they ask?
