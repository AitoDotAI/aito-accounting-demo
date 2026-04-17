"""FastAPI application — Aito accounting demo backend.

Thin API layer that delegates to the Aito client. Each endpoint is
a direct window into an Aito capability, not an abstraction over it.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.aito_client import AitoClient, AitoError
from src.config import load_config

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
