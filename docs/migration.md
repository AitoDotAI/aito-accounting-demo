# Migration playbook — leaving Aito if you ever need to

The most-asked unspoken question from enterprise CTOs evaluating
any predictive database is *"what if you go away?"*. This doc
exists so the answer is "here's the migration plan, three pages,
no surprises" instead of a sales conversation.

It's not a commitment to migrate. It's a written record that
migration is feasible and bounded.

## What's tied to Aito

The Predictive Ledger demo uses Aito for four things:

| What | Aito operator | What replaces it off-Aito |
|------|--------------|-----------------------------|
| GL code + approver predictions | `_predict` | Postgres + scikit-learn (LogisticRegression / GradientBoosting) |
| Rule mining | `_relate` | Postgres GROUP BY + lift formula |
| Help article CTR ranking | `_recommend` | LightGBM ranker over impressions |
| Held-out accuracy measurement | `_evaluate` | scikit-learn `cross_val_score` |

The bulk of the system is **not Aito-specific**: FastAPI backend,
Next.js frontend, schema, fixture generator, CSS, the entire
nine-view UI. None of that needs migration work.

## Step 1 — Export your Aito data to CSV

Every Aito table can be dumped to JSON (and from there to CSV)
via `_search` with no `where` and a high `limit`. The data
loader's schema definitions in `src/data_loader.py` map directly
to standard relational tables.

```python
# scripts/export_aito_to_csv.py
import csv, json
from src.aito_client import AitoClient
from src.config import load_config

client = AitoClient(load_config())
for table in ["customers", "invoices", "bank_transactions",
              "overrides", "help_articles", "help_impressions"]:
    rows = []
    cursor = 0
    while True:
        r = client.search(table, {}, limit=10_000, offset=cursor)
        hits = r.get("hits", [])
        if not hits:
            break
        rows.extend(hits)
        cursor += len(hits)
    with open(f"export/{table}.csv", "w") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"{table}: {len(rows)} rows")
```

Throughput: ~5 000 rows/s on commodity hardware. 1 M-row dump
takes ~3 minutes.

## Step 2 — Replace `_predict` with Postgres + scikit-learn

```python
# src/invoice_service.py — drop-in replacement
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
import pickle

class GLPredictor:
    """Replaces predict_invoice() in invoice_service.py."""
    def __init__(self, model_path):
        self.vec, self.model = pickle.load(open(model_path, "rb"))

    def predict(self, invoice: dict) -> tuple[str, float]:
        features = {
            f"vendor={invoice['vendor']}": 1,
            f"category={invoice.get('category', '')}": 1,
            "amount_log": np.log1p(invoice["amount"]),
            # description tokens
            **{f"desc_{t}": 1 for t in invoice.get("description", "").lower().split()},
        }
        X = self.vec.transform([features])
        proba = self.model.predict_proba(X)[0]
        idx = proba.argmax()
        return self.model.classes_[idx], float(proba[idx])
```

A nightly job re-fits the model from the Postgres data:

```python
# scripts/train_gl_model.py
df = pd.read_sql("SELECT * FROM invoices WHERE customer_id = %s", conn, params=[cid])
X = vec.fit_transform(df.apply(features, axis=1))
y = df["gl_code"]
model = LogisticRegression(max_iter=1000).fit(X, y)
pickle.dump((vec, model), open(f"models/{cid}.pkl", "wb"))
```

You'd train one model per customer (Aito's where-clause filter
becomes a separate model file). For 255 customers that's ~10
minutes of training/night.

**What you lose** vs Aito:
- No more "add a row, next query reflects it" — you're back on
  a nightly retrain cycle.
- `$why` becomes the model's feature importances, which are less
  interpretable than Aito's lift breakdown for non-linear models.
- Per-prediction calibration changes — scikit-learn's
  `predict_proba` is decent for logistic regression but
  notoriously overconfident for tree-based models without
  `CalibratedClassifierCV`.

## Step 3 — Replace `_relate` with SQL

```sql
-- Equivalent of: _relate from invoices where category=telecom relate gl_code
SELECT
  gl_code,
  COUNT(*) AS f_on_condition,
  (SELECT COUNT(*) FROM invoices WHERE customer_id = $1 AND category = 'telecom') AS f_condition,
  COUNT(*) * 1.0 /
    (SELECT COUNT(*) FROM invoices WHERE customer_id = $1 AND category = 'telecom') AS p_on_condition,
  (COUNT(*) * 1.0 / (SELECT COUNT(*) FROM invoices WHERE customer_id = $1 AND category = 'telecom'))
    /
    (SELECT COUNT(*) FROM invoices WHERE customer_id = $1 AND gl_code = i.gl_code) * 1.0 /
    (SELECT COUNT(*) FROM invoices WHERE customer_id = $1) AS lift
FROM invoices i
WHERE customer_id = $1 AND category = 'telecom'
GROUP BY gl_code
ORDER BY lift DESC;
```

The `_relate` shape is a SQL pivot. Slower than Aito's index lookup
on big tables (full scan vs O(log n)) but the result is identical.

For chained `_relate` (the rule-mining drill), it's a `WHERE` AND
of multiple conditions. Same query template, more `AND`s.

## Step 4 — Replace `_recommend` with LightGBM

For the help drawer ranking:

```python
# src/help_service.py — drop-in replacement
import lightgbm as lgb

# Training: each impression is one row, label = clicked,
# group = (customer_id, page, query) tuple
X = impressions[["customer_id", "page", "query", "article_id", "prev_article_id"]]
y = impressions["clicked"]
groups = impressions.groupby(["customer_id", "page", "query"]).size().tolist()
model = lgb.LGBMRanker().fit(X, y, group=groups)

# Inference: rank candidate articles for a (customer, page, query)
def search_help(customer_id, page, query):
    candidates = articles_eligible_for(customer_id)
    X = pd.DataFrame([{
        "customer_id": customer_id, "page": page, "query": query,
        "article_id": a, "prev_article_id": None,
    } for a in candidates])
    scores = model.predict(X)
    return [a for _, a in sorted(zip(scores, candidates), reverse=True)[:5]]
```

Roughly 1-2 days of work. LightGBM rankers are widely deployed and
the training data (impressions table) is unchanged.

## Step 5 — Replace `_evaluate` with scikit-learn

```python
from sklearn.model_selection import cross_val_score
scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
```

The per-case green/red diff in the Quality Predictions view becomes
a `.predict()` over a held-out sample with a confusion matrix.

## What stays unchanged

The migration touches `src/invoice_service.py`,
`src/quality_service.py`, `src/help_service.py`,
`src/anomaly_service.py`. Everything else (FastAPI app, Next.js
frontend, schema, fixture generator, CSS, all 9 views, the
master-detail dock, the `$why` cards, the customer dropdown,
multi-tenancy via `where: {customer_id}`, ADRs, deployment) keeps
working unchanged.

## Estimated migration cost

- **CSV export**: 1 day
- **GL/approver predictions** (LogisticRegression + per-customer
  pickle): 3-5 days
- **Rule mining** (SQL pivots + lift): 2 days
- **Help ranking** (LightGBM): 2 days
- **Evaluate / quality views** (sklearn cross_val): 1-2 days
- **Test pass + reload + redeploy**: 2-3 days

**Total: ~2 working weeks**, with no UI rework.

## Why this matters at procurement time

The exit cost is **bounded and known**. Aito's licence is fixed,
on-prem, and your data is in your database — there's no SaaS lock,
no proprietary data format, no contractual barrier to leaving.
That's a lighter contractual posture than most SaaS predictive
products, and it's worth saying out loud in the procurement
conversation.

You probably won't migrate. But the conversation goes better when
"and if we ever need to leave" is a 2-week project, not an
unknown.
