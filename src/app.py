"""FastAPI application — Aito accounting demo backend.

Thin API layer that delegates to the Aito client. Each endpoint is
a direct window into an Aito capability, not an abstraction over it.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.aito_client import AitoClient, AitoError
from src.config import load_config
from src.invoice_service import (
    DEMO_INVOICES,
    compute_metrics,
    predict_batch,
)

config = load_config()
aito = AitoClient(config)

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
    predictions = predict_batch(aito, DEMO_INVOICES)
    metrics = compute_metrics(predictions)

    return {
        "invoices": [p.to_dict() for p in predictions],
        "metrics": metrics,
    }
