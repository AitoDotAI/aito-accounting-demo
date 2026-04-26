"""Predictive Ledger — Multi-tenant Aito Demo API.

Every endpoint accepts customer_id to scope predictions to a specific
customer's data. This demonstrates single-table multi-tenancy where
Aito isolates predictions via the where clause.

Form Fill calls Aito live. Other views can use pre-computed data
(if available) or call Aito live.
"""

import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.aito_client import AitoClient, AitoError
from src import cache
from src.config import load_config
from src.formfill_service import KNOWN_VENDORS, predict_fields
from src.invoice_service import predict_batch, compute_metrics
from src.matching_service import match_all
from src.rulemining_service import mine_rules
from src.anomaly_service import scan_all
from src.quality_service import get_quality_overview
from src.rate_limit import check_rate_limit

config = load_config()
aito = AitoClient(config)

# Initialize two-layer cache: in-memory L1 + Aito-persistent L2
cache.init(aito)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _warm_top_customers():
    """Warm cache for top customers on startup."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    def warm():
        if not aito.check_connectivity():
            return
        # Get all customers, pick top 5 by invoice count
        try:
            r = aito.search("customers", {}, limit=300)
            top_customers = sorted(r.get("hits", []), key=lambda c: -c.get("invoice_count", 0))[:5]
        except Exception as e:
            print(f"warmup: cannot list customers: {e}")
            return

        from src.invoice_service import predict_invoice, compute_metrics

        def warm_one(cust, deep=False):
            cid = cust["customer_id"]
            try:
                # Fast: invoices + quality (always)
                result = aito.search("invoices", {"customer_id": cid}, limit=20)
                with ThreadPoolExecutor(max_workers=8) as pool:
                    preds = list(pool.map(
                        lambda inv: predict_invoice(aito, {**inv, "customer_id": cid}),
                        result.get("hits", []),
                    ))
                data = {"invoices": [p.to_dict() for p in preds], "metrics": compute_metrics(preds)}
                cache.set(f"invoices:{cid}", data)
                cache.set(f"quality:{cid}", get_quality_overview(aito, customer_id=cid))

                # Deep: matching + anomalies + rules (only for top customers)
                if deep:
                    cache.set(f"matching:{cid}", match_all(aito, customer_id=cid))
                    cache.set(f"anomalies:{cid}", scan_all(aito, customer_id=cid))
                    cache.set(f"rules:{cid}", mine_rules(aito, customer_id=cid))
                    print(f"  {cid}: cached (deep)")
                else:
                    print(f"  {cid}: cached (fast)")
            except Exception as e:
                print(f"  {cid} error: {e}")

        # Warm top 3 deeply (all views), customers 4-5 fast only
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = []
            for i, cust in enumerate(top_customers):
                deep = i < 3
                futures.append(pool.submit(warm_one, cust, deep))
            for f in futures:
                f.result()

    threading.Thread(target=warm, daemon=True).start()


_warm_top_customers()

# ── App setup ─────────────────────────────────────────────────────

app = FastAPI(
    title="Predictive Ledger — Aito Demo API",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip):
            return JSONResponse(status_code=429, content={"error": "Rate limit exceeded."})
    return await call_next(request)


# ── Customer list ─────────────────────────────────────────────────

@app.get("/api/cache/status")
def cache_status(customer_id: str = Query(...)):
    """Check whether a customer's data is warmed in cache."""
    return {
        "customer_id": customer_id,
        "invoices_warm": cache.get(f"invoices:{customer_id}") is not None,
        "quality_warm": cache.get(f"quality:{customer_id}") is not None,
        "matching_warm": cache.get(f"matching:{customer_id}") is not None,
        "rules_warm": cache.get(f"rules:{customer_id}") is not None,
        "anomalies_warm": cache.get(f"anomalies:{customer_id}") is not None,
    }


@app.get("/api/customers")
def list_customers():
    """List all customers with their sizes."""
    try:
        result = aito.search("customers", {}, limit=300)
        customers = result.get("hits", [])
        # Sort by invoice_count descending
        customers.sort(key=lambda c: c.get("invoice_count", 0), reverse=True)
        return {"customers": customers, "total": len(customers)}
    except AitoError as exc:
        return {"error": str(exc)}


# ── Per-customer endpoints ────────────────────────────────────────

@app.get("/api/health")
def health():
    cached = cache.get("health")
    if cached:
        return cached
    connected = aito.check_connectivity()
    result = {"status": "ok", "aito_connected": connected, "aito_url": config.aito_api_url}
    cache.set("health", result, ttl=60)
    return result


@app.get("/api/invoices/pending")
def invoices_pending(customer_id: str = Query(...), page: int = 1, per_page: int = 20):
    """Predict GL code and approver for pending invoices."""
    cache_key = f"invoices:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        data = cached
    else:
        # Fetch only one page worth of invoices — lazy loading
        try:
            result = aito.search("invoices", {"customer_id": customer_id}, limit=per_page)
            sample_invoices = result.get("hits", [])
        except AitoError:
            return {"invoices": [], "metrics": {}, "error": "Could not fetch invoices"}

        # Parallelize predictions for faster response
        from concurrent.futures import ThreadPoolExecutor
        from src.invoice_service import predict_invoice
        with ThreadPoolExecutor(max_workers=8) as pool:
            predictions = list(pool.map(
                lambda inv: predict_invoice(aito, {**inv, "customer_id": customer_id}),
                sample_invoices,
            ))
        metrics = compute_metrics(predictions)
        data = {"invoices": [p.to_dict() for p in predictions], "metrics": metrics}
        cache.set(cache_key, data, ttl=300)

    invoices = data.get("invoices", [])
    total = len(invoices)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "invoices": invoices[start:end],
        "metrics": data.get("metrics", {}),
        "pagination": {"page": page, "per_page": per_page, "total": total},
    }


@app.get("/api/matching/pairs")
def matching_pairs(customer_id: str = Query(...)):
    """Match bank transactions to invoices for a customer."""
    cache_key = f"matching:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = match_all(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/rules/candidates")
def rules_candidates(customer_id: str = Query(...)):
    """Mine rule candidates for a customer."""
    cache_key = f"rules:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = mine_rules(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/anomalies/scan")
def anomalies_scan(customer_id: str = Query(...)):
    """Scan invoices for anomalies for a customer."""
    cache_key = f"anomalies:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = scan_all(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/quality/overview")
def quality_overview(customer_id: str = Query(...)):
    """Quality metrics for a customer."""
    cache_key = f"quality:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = get_quality_overview(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/quality/predictions")
def quality_predictions(customer_id: str = Query(...)):
    """Real prediction accuracy via Aito _evaluate, with rules-only baseline.

    Compares Aito's predictions to ground-truth GL codes on a held-out
    test set, then replays the static rules engine on the same set to
    show the rules-only baseline.
    """
    cache_key = f"predictions:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    from src.quality_service import compute_prediction_quality
    result = compute_prediction_quality(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=600)
    return result


@app.get("/api/quality/rules")
def quality_rules(customer_id: str = Query(...)):
    """Rule performance — replay each static rule against actual GL codes."""
    cache_key = f"rules_perf:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    from src.quality_service import compute_rule_performance
    result = compute_rule_performance(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=600)
    return result


# ── Live Aito endpoints ──────────────────────────────────────────

@app.get("/api/formfill/vendors")
def formfill_vendors(customer_id: str = Query(...)):
    """Return vendors used by this customer."""
    try:
        result = aito.search("invoices", {"customer_id": customer_id}, limit=100)
        vendors = sorted({hit["vendor"] for hit in result.get("hits", [])})
        return {"vendors": vendors}
    except AitoError:
        return {"vendors": KNOWN_VENDORS}


@app.get("/api/formfill/template")
def formfill_template(customer_id: str = Query(...), vendor: str = Query(...)):
    """Predict the most common historical template for a vendor.

    Returns the joint mode of all classification fields when there is enough
    historical data. The UI shows this as 'Looks like your monthly Telia
    invoice. [Apply]' — one click fills all fields.
    """
    from src.formfill_service import predict_template
    template = predict_template(aito, customer_id, vendor)
    return template or {"error": "not enough history"}


@app.post("/api/formfill/predict")
def formfill_predict(body: dict):
    """Predict form fields — live Aito call with customer_id."""
    from src.formfill_service import INPUT_FIELDS
    customer_id = body.get("customer_id", "")
    where = {k: v for k, v in body.items() if k in INPUT_FIELDS and v}
    if customer_id:
        where["customer_id"] = customer_id
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
    try:
        return aito.get_schema()
    except AitoError as exc:
        return {"error": str(exc)}


# ── Serve frontend ────────────────────────────────────────────────

_frontend_dir = _PROJECT_ROOT / "frontend" / "out"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
