"""Per-domain interactive evaluation, mirroring aito-demo/EvaluationPage.

The page lets the user pick a domain (Invoice Processing, Payment
Matching, Help recommendations), pick a prediction target field
inside that domain, and pick which input features to condition on.
The backend runs Aito `_evaluate` with `select: [..., "cases"]` so
per-case results are returned alongside the aggregate KPIs.

Caching: results keyed by (customer_id, domain, predict, sorted
input_fields, train_pct, limit). 10-minute TTL.
"""

from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient, AitoError


# Domain catalog: which tables/fields are evaluable, what defaults to use.
# Fields listed here must exist in the schema (see src/data_loader.py).
DOMAINS: dict[str, dict] = {
    "invoices": {
        "label": "Invoice Processing",
        "table": "invoices",
        "id_field": "invoice_id",
        "predict_targets": [
            {"field": "gl_code", "label": "GL code"},
            {"field": "approver", "label": "Approver"},
            {"field": "cost_centre", "label": "Cost centre"},
            {"field": "category", "label": "Category"},
            {"field": "vat_pct", "label": "VAT rate"},
            {"field": "payment_method", "label": "Payment method"},
        ],
        "input_fields": [
            {"field": "vendor", "label": "Vendor", "default": True},
            {"field": "amount", "label": "Amount", "default": True},
            {"field": "category", "label": "Category", "default": True},
            {"field": "vendor_country", "label": "Vendor country", "default": False},
            {"field": "vat_pct", "label": "VAT %", "default": False},
            {"field": "payment_method", "label": "Payment method", "default": False},
            {"field": "description", "label": "Description", "default": False},
        ],
        "display_columns": [
            {"field": "invoice_id", "label": "ID", "mono": True},
            {"field": "vendor", "label": "Vendor"},
            {"field": "amount", "label": "Amount", "mono": True, "format": "money"},
            {"field": "category", "label": "Category"},
        ],
    },
    "matching": {
        "label": "Payment Matching",
        "table": "bank_transactions",
        "id_field": "transaction_id",
        "predict_targets": [
            {"field": "vendor_name", "label": "Vendor name"},
            {"field": "invoice_id", "label": "Linked invoice"},
        ],
        "input_fields": [
            {"field": "description", "label": "Bank description", "default": True},
            {"field": "amount", "label": "Amount", "default": True},
            {"field": "bank", "label": "Bank", "default": False},
        ],
        "display_columns": [
            {"field": "transaction_id", "label": "ID", "mono": True},
            {"field": "description", "label": "Description"},
            {"field": "amount", "label": "Amount", "mono": True, "format": "money"},
            {"field": "bank", "label": "Bank"},
        ],
    },
    "help": {
        "label": "Help Recommendations",
        "table": "help_impressions",
        "id_field": "impression_id",
        "predict_targets": [
            {"field": "clicked", "label": "Click prediction"},
            {"field": "article_id", "label": "Article id"},
        ],
        "input_fields": [
            {"field": "page", "label": "Page", "default": True},
            {"field": "article_id", "label": "Article id", "default": True},
            {"field": "query", "label": "Query", "default": False},
        ],
        "display_columns": [
            {"field": "impression_id", "label": "ID", "mono": True, "truncate": True},
            {"field": "page", "label": "Page", "mono": True},
            {"field": "article_id", "label": "Article", "mono": True},
        ],
    },
}


def get_domains_catalog() -> dict:
    """Return the domain catalog for the frontend configurator."""
    return {"domains": [
        {
            "key": k,
            "label": d["label"],
            "table": d["table"],
            "predict_targets": d["predict_targets"],
            "input_fields": d["input_fields"],
            "display_columns": d["display_columns"],
        }
        for k, d in DOMAINS.items()
    ]}


def run_evaluation(
    client: AitoClient,
    customer_id: str,
    domain: str,
    predict: str,
    input_fields: list[str],
    limit: int = 100,
) -> dict:
    """Run Aito _evaluate for one (domain, predict, input_fields) combo.

    Uses `testSource` to bound the test set, which is the user's hint
    plus what we already do in book/test_05_evaluate.py. With
    `select: [..., "cases"]` Aito returns per-case predictions
    alongside aggregate KPIs.

    Returns:
        kpis: accuracy, baseAccuracy, accuracyGain, meanRank,
              testSamples, geomMeanP, errorRate
        cases: list of {invoice_id-or-similar, inputs, actual,
              predicted, $p, correct}
        meta:  {operator, query} so the frontend can display it
    """
    if domain not in DOMAINS:
        return {"error": f"Unknown domain: {domain}"}
    cfg = DOMAINS[domain]
    table = cfg["table"]

    # Build the where clause: customer_id + each $get-bound input field
    where: dict = {"customer_id": customer_id}
    for f in input_fields:
        where[f] = {"$get": f}

    query = {
        "testSource": {
            "from": table,
            "where": {"customer_id": customer_id},
            "limit": limit,
        },
        "evaluate": {
            "from": table,
            "where": where,
            "predict": predict,
        },
        "select": [
            "accuracy",
            "baseAccuracy",
            "accuracyGain",
            "meanRank",
            "geomMeanP",
            "testSamples",
            "trainSamples",
            "cases",
        ],
    }

    try:
        result = client._request("POST", "/_evaluate", json=query)
    except AitoError as exc:
        return {"error": str(exc), "query": query}

    accuracy = float(result.get("accuracy", 0))
    base_accuracy = float(result.get("baseAccuracy", 0))
    test_samples = int(result.get("testSamples", 0))
    cases_raw = result.get("cases", [])

    # Aito _evaluate cases (verified via debug): each case has
    #   testCase: { ...full row including the actual predicted value }
    #   accurate: bool — whether the top prediction was correct
    #   top:      { feature, $p, field } — Aito's top prediction
    #   correct:  { feature, $p, field } — the actual answer + its
    #             predicted probability under the model
    cases: list[dict] = []
    for case in cases_raw:
        row = case.get("testCase", {}) or {}
        actual = row.get(predict)
        top = case.get("top") or {}
        predicted = top.get("feature")
        confidence = float(top.get("$p", 0) or 0)
        is_correct = bool(case.get("accurate", actual == predicted))
        cases.append({
            "row_id": row.get(cfg["id_field"]),
            "row": row,
            "actual": actual,
            "predicted": predicted,
            "confidence": round(confidence, 3),
            "correct": is_correct,
        })

    correct_count = sum(1 for c in cases if c["correct"])

    return {
        "kpis": {
            "accuracy_pct": round(accuracy * 100, 2),
            "base_accuracy_pct": round(base_accuracy * 100, 2),
            "accuracy_gain_pct": round(float(result.get("accuracyGain", accuracy - base_accuracy)) * 100, 2),
            "mean_rank": round(float(result.get("meanRank", 0)), 2),
            "geom_mean_p": round(float(result.get("geomMeanP", 0)), 4),
            "test_samples": test_samples,
            "train_samples": int(result.get("trainSamples", 0)),
            "correct_predictions": correct_count if cases else round(accuracy * test_samples),
            "error_rate_pct": round((1 - accuracy) * 100, 2),
        },
        "cases": cases[: min(50, len(cases))],  # cap UI table to 50 rows
        "meta": {
            "domain": domain,
            "domain_label": cfg["label"],
            "table": table,
            "predict": predict,
            "input_fields": input_fields,
            "operator": "_evaluate",
            "query": query,
            "id_field": cfg["id_field"],
            "display_columns": cfg["display_columns"],
        },
    }
