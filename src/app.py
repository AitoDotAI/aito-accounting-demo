"""Predictive Ledger — Aito Demo API.

Serves pre-computed predictions from data/precomputed/ for all views
except Form Fill, which calls Aito live for interactive predictions.

This design means: instant startup, no warmup, no cache management,
and the demo works even if Aito is temporarily slow.
"""

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.aito_client import AitoClient, AitoError
from src import cache
from src.config import load_config
from src.formfill_service import KNOWN_VENDORS, predict_fields
from src.rate_limit import check_rate_limit

config = load_config()
aito = AitoClient(config)

# ── Load pre-computed data ────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRECOMPUTED_DIR = _PROJECT_ROOT / "data" / "precomputed"
_precomputed: dict[str, dict] = {}


def _load_precomputed(name: str) -> dict:
    """Load a pre-computed JSON file. Cached in memory after first read."""
    if name not in _precomputed:
        path = _PRECOMPUTED_DIR / f"{name}.json"
        if path.exists():
            with open(path) as f:
                _precomputed[name] = json.load(f)
        else:
            _precomputed[name] = {"error": f"Precomputed data not found: {name}. Run: python data/precompute_predictions.py"}
    return _precomputed[name]


# ── App setup ─────────────────────────────────────────────────────

app = FastAPI(
    title="Predictive Ledger — Aito Demo API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit API requests to protect the Aito API key."""
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Try again in a minute."},
            )
    return await call_next(request)


# ── Pre-computed endpoints (instant, no Aito calls) ───────────────

@app.get("/api/health")
def health():
    """Check backend status."""
    precomputed_ready = (_PRECOMPUTED_DIR / "invoices_pending.json").exists()
    return {
        "status": "ok",
        "precomputed_data": precomputed_ready,
        "aito_url": config.aito_api_url,
    }


@app.get("/api/invoices/pending")
def invoices_pending(page: int = 1, per_page: int = 20):
    """Return pending invoices with predictions. Paginated."""
    data = _load_precomputed("invoices_pending")
    if "error" in data:
        return data

    invoices = data.get("invoices", [])
    total = len(invoices)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "invoices": invoices[start:end],
        "metrics": data.get("metrics", {}),
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": (total + per_page - 1) // per_page},
    }


@app.get("/api/matching/pairs")
def matching_pairs():
    """Return pre-computed invoice ↔ bank transaction matches."""
    return _load_precomputed("matching_pairs")


@app.get("/api/rules/candidates")
def rules_candidates():
    """Return pre-computed rule candidates from _relate."""
    return _load_precomputed("rules_candidates")


@app.get("/api/anomalies/scan")
def anomalies_scan():
    """Return pre-computed anomaly flags from inverse _predict."""
    return _load_precomputed("anomalies_scan")


@app.get("/api/quality/overview")
def quality_overview():
    """Return pre-computed quality metrics."""
    return _load_precomputed("quality_overview")


@app.get("/api/quality/predictions")
def quality_predictions():
    """Return pre-computed prediction accuracy metrics."""
    return _load_precomputed("prediction_accuracy")


@app.get("/api/quality/rules")
def quality_rules():
    """Return pre-computed rule performance metrics."""
    return _load_precomputed("rule_performance")


# ── Live Aito endpoints (interactive) ─────────────────────────────

@app.get("/api/formfill/vendors")
def formfill_vendors():
    """Return known vendors for the form fill dropdown."""
    return {"vendors": KNOWN_VENDORS}


@app.post("/api/formfill/predict")
def formfill_predict(body: dict):
    """Predict form fields from any combination of known fields.

    This is the ONLY endpoint that calls Aito live — it's the
    interactive showcase of real-time predictions.
    """
    from src.formfill_service import INPUT_FIELDS
    where = {k: v for k, v in body.items() if k in INPUT_FIELDS and v}
    if not where:
        return {"error": "at least one field is required"}

    cache_key = "formfill:" + json.dumps(where, sort_keys=True)
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = predict_fields(aito, where)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/schema")
def schema():
    """Return the Aito database schema."""
    try:
        return aito.get_schema()
    except AitoError as exc:
        return {"error": str(exc), "status_code": exc.status_code}


# ── Serve Next.js static export ───────────────────────────────────

_frontend_dir = _PROJECT_ROOT / "frontend" / "out"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
