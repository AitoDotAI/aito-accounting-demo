"""FastAPI application — Aito accounting demo backend.

Thin API layer that delegates to the Aito client. Each endpoint is
a direct window into an Aito capability, not an abstraction over it.

Serves the Next.js static export from frontend/out/ when available.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.aito_client import AitoClient, AitoError
from src.anomaly_service import scan_all
from src import cache
from src.config import load_config
from src.quality_service import get_quality_overview
from src.formfill_service import KNOWN_VENDORS, predict_fields
from src.invoice_service import DEMO_INVOICES, compute_metrics, predict_batch
from src.matching_service import match_all
from src.rulemining_service import mine_rules

config = load_config()
aito = AitoClient(config)


def _warm_cache() -> None:
    """Pre-compute all cacheable endpoints on startup.

    This avoids the slow first-load experience where 50+ Aito calls
    run sequentially while the user stares at "Loading...".
    """
    import threading

    def warm():
        try:
            if not aito.check_connectivity():
                return
            print("Warming cache...")
            predictions = predict_batch(aito, DEMO_INVOICES)
            cache.set("invoices_pending", {
                "invoices": [p.to_dict() for p in predictions],
                "metrics": compute_metrics(predictions),
            })
            cache.set("matching_pairs", match_all(aito))
            cache.set("rules_candidates", mine_rules(aito))
            cache.set("anomalies_scan", scan_all(aito))
            cache.set("quality_overview", get_quality_overview(aito))
            print("Cache warm.")
        except Exception as e:
            print(f"Cache warmup failed: {e}")

    threading.Thread(target=warm, daemon=True).start()


_warm_cache()

app = FastAPI(
    title="Ledger Pro — Aito Demo API",
    version="0.1.0",
)

# Allow the HTML demo to call the API from file:// or localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Check backend and Aito connectivity."""
    connected = aito.check_connectivity()
    return {
        "status": "ok",
        "aito_connected": connected,
        "aito_url": config.aito_api_url,
    }


@app.get("/api/schema")
def schema():
    """Return the Aito database schema — shows what tables and fields exist."""
    try:
        return aito.get_schema()
    except AitoError as exc:
        return {"error": str(exc), "status_code": exc.status_code}


@app.get("/api/invoices/pending")
def invoices_pending():
    """Return pending invoices with live Aito predictions.

    Each invoice gets a predicted GL code and approver, with confidence
    scores and source classification (rule/aito/review).
    """
    cached = cache.get("invoices_pending")
    if cached:
        return cached

    predictions = predict_batch(aito, DEMO_INVOICES)
    metrics = compute_metrics(predictions)

    result = {
        "invoices": [p.to_dict() for p in predictions],
        "metrics": metrics,
    }
    cache.set("invoices_pending", result)
    return result


@app.get("/api/formfill/vendors")
def formfill_vendors():
    """Return known vendors for the form fill dropdown."""
    return {"vendors": KNOWN_VENDORS}


@app.post("/api/formfill/predict")
def formfill_predict(body: dict):
    """Predict form fields from any combination of known fields.

    Accepts any subset: {"vendor": "Kesko Oyj"} or {"amount": 4220}
    or {"vendor": "Kesko Oyj", "gl_code": "4400"}.

    Returns predictions for fields NOT provided in the request,
    each with top-3 alternatives and $why explanations.
    """
    from src.formfill_service import INPUT_FIELDS
    where = {k: v for k, v in body.items() if k in INPUT_FIELDS and v}
    if not where:
        return {"error": "at least one field is required"}

    return predict_fields(aito, where)


@app.get("/api/matching/pairs")
def matching_pairs():
    """Match open invoices to bank transactions.

    Returns matched, suggested, and unmatched pairs with confidence
    scores based on vendor name similarity and amount proximity.
    """
    cached = cache.get("matching_pairs")
    if cached:
        return cached
    result = match_all(aito)
    cache.set("matching_pairs", result)
    return result


@app.get("/api/rules/candidates")
def rules_candidates():
    """Mine rule candidates from invoice data using Aito _relate.

    Returns patterns with support ratios, coverage, and strength
    classification. Each candidate represents a potential rule:
    "when condition X is true, GL code is Y (N/M times)".
    """
    cached = cache.get("rules_candidates")
    if cached:
        return cached
    result = mine_rules(aito)
    cache.set("rules_candidates", result)
    return result


@app.get("/api/anomalies/scan")
def anomalies_scan():
    """Scan invoices for anomalies using inverse prediction.

    Predicts GL code and approver for each invoice. Low confidence
    means the invoice doesn't fit known patterns — that's the
    anomaly signal. No separate anomaly model needed.
    """
    cached = cache.get("anomalies_scan")
    if cached:
        return cached
    result = scan_all(aito)
    cache.set("anomalies_scan", result)
    return result


@app.get("/api/quality/overview")
def quality_overview():
    """Aggregate quality metrics for the dashboard.

    Returns automation breakdown, override statistics, and emerging
    patterns from override data — closing the feedback loop.
    """
    cached = cache.get("quality_overview")
    if cached:
        return cached
    result = get_quality_overview(aito)
    cache.set("quality_overview", result)
    return result


# Serve Next.js static export — must come after all API routes
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "out"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
