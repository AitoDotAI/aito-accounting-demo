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
from src import cache, precomputed
from src.config import load_config
from src.formfill_service import predict_fields
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

# Aito-backed precompute store. Writes from `./do precompute` land
# in an Aito table; the running container reads from there on first
# hit, falling back to the shipped bootstrap JSON when Aito is
# briefly unreachable. See src/precompute_store.py.
from src import precompute_store  # noqa: E402
precompute_store.init(aito)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _warm_aito_tables():
    """Take the cold-load cost off the first user's path.

    Aito lazily loads tables on first query; help_impressions in
    particular goes 12s → 14ms after the first hit. We fire one
    cheap _search per live-queried table on startup so a real
    visitor doesn't watch a 12s spinner. See
    docs/notes/aito-perf-findings.md.
    """
    import threading

    def go():
        if not aito.check_connectivity():
            return
        for table in ("help_impressions", "help_articles", "customers"):
            try:
                aito.search(table, {}, limit=1)
            except Exception as e:
                print(f"warm-table {table}: {e}")

    threading.Thread(target=go, daemon=True).start()


_warm_aito_tables()


def _warm_top_customers():
    """Warm cache for top customers on startup.

    Skipped entirely when data/precomputed/ contains any customer
    folder — precomputed JSON serves as the warm layer.
    """
    if (_PROJECT_ROOT / "data" / "precomputed").is_dir() and any(
        (_PROJECT_ROOT / "data" / "precomputed").iterdir()
    ):
        print("Precomputed data found — skipping cache warmup.")
        return

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
        from src.quality_service import mine_rules_for_customer

        def warm_one(cust, deep=False):
            cid = cust["customer_id"]
            try:
                # Mine per-customer rules once and cache for downstream use
                mined = mine_rules_for_customer(aito, cid)
                cache.set(f"mined_rules:{cid}", mined, ttl=1800)

                # Fast: invoices + quality (always)
                result = aito.search("invoices", {"customer_id": cid}, limit=20)
                with ThreadPoolExecutor(max_workers=8) as pool:
                    preds = list(pool.map(
                        lambda inv: predict_invoice(aito, {**inv, "customer_id": cid}, rules=mined),
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
    expose_headers=["X-Aito-Ms", "X-Aito-Calls", "X-Aito-Ops"],
)


@app.middleware("http")
async def aito_latency_middleware(request: Request, call_next):
    """Tag each /api response with the time spent in Aito calls.

    A contextvar accumulator collects per-Aito-call ms inside
    `AitoClient._request`; this middleware reads it after the
    handler runs and exposes the total + count via two response
    headers. Frontend uses these to render a topbar latency
    badge — the demo's persistent answer to "is the predictive
    layer actually fast?". Endpoints that don't hit Aito set no
    headers (and the frontend skips them).
    """
    from src.aito_client import aito_call_log
    log: list[tuple[str, float]] = []
    token = aito_call_log.set(log)
    try:
        response = await call_next(request)
    finally:
        aito_call_log.reset(token)
    if log:
        total_ms = sum(ms for _, ms in log)
        response.headers["X-Aito-Ms"] = f"{total_ms:.1f}"
        response.headers["X-Aito-Calls"] = str(len(log))
        # Per-call breakdown for the latency overlay. Format:
        # "_predict:28.4,_relate:142.0,_search:11.2".
        # Path → op: "/_predict" → "_predict"; "/data/x/file" → "data:x:file".
        def _op_label(path: str) -> str:
            return path.lstrip("/").replace("/", ":")
        response.headers["X-Aito-Ops"] = ",".join(
            f"{_op_label(p)}:{ms:.1f}" for p, ms in log
        )
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip):
            return JSONResponse(status_code=429, content={"error": "Rate limit exceeded."})
    return await call_next(request)


@app.middleware("http")
async def validate_customer_middleware(request: Request, call_next):
    """Reject requests with an empty or unknown customer_id with 400.

    Per CLAUDE.md prime directive #2 -- never silently coerce or
    discard unexpected data. A frontend bug that drops customer_id
    should surface immediately, not show "no invoices" for 30
    seconds.
    """
    if request.url.path.startswith("/api/") and "customer_id" in request.query_params:
        cid = request.query_params.get("customer_id", "")
        if not cid:
            return JSONResponse(
                status_code=400,
                content={"error": "customer_id query parameter is required and must be non-empty"},
            )
        known = _load_known_customers()
        if known and cid not in known:
            return JSONResponse(
                status_code=400,
                content={"error": f"unknown customer_id: {cid!r}"},
            )
    return await call_next(request)


# ── Health / keep-warm ────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    """Cheap liveness check for keep-warm pingers.

    Azure App Service idles containers to zero after ~20 min of no
    traffic; the cold-start (~10 s) is the dominant first-paint
    latency on the deployed demo. Hitting /healthz on a 4-minute
    cron from a free uptime service keeps the instance warm without
    triggering any Aito calls.
    """
    return {"ok": True}


# ── Customer list ─────────────────────────────────────────────────

@app.get("/api/cache/status")
def cache_status(customer_id: str = Query(...)):
    """Check whether a customer's data is precomputed (instant) or
    will fall back to live Aito (slow)."""
    return {
        "customer_id": customer_id,
        "invoices_warm": (
            precomputed.has(customer_id, "invoices_pending")
            or cache.get(f"invoices:{customer_id}") is not None
        ),
        "quality_warm": (
            precomputed.has(customer_id, "quality_overview")
            or cache.get(f"quality:{customer_id}") is not None
        ),
        "matching_warm": (
            precomputed.has(customer_id, "matching_pairs")
            or cache.get(f"matching:{customer_id}") is not None
        ),
        "rules_warm": (
            precomputed.has(customer_id, "rules_candidates")
            or cache.get(f"rules:{customer_id}") is not None
        ),
        "anomalies_warm": (
            precomputed.has(customer_id, "anomalies_scan")
            or cache.get(f"anomalies:{customer_id}") is not None
        ),
    }


@app.get("/api/cache/warm_customers")
def warm_customers():
    """Customer ids that have precomputed JSON (instant load).

    Drives the dot indicator in the customer dropdown so a developer
    evaluator can see at a glance which customers will be fast.
    """
    base = _PROJECT_ROOT / "data" / "precomputed"
    if not base.is_dir():
        return {"customer_ids": []}
    ids = sorted(p.name for p in base.iterdir() if p.is_dir())
    return {"customer_ids": ids}


_KNOWN_CUSTOMER_IDS: set[str] | None = None


def _load_known_customers() -> set[str]:
    """Cache the list of valid customer ids so the validator doesn't
    hit Aito on every request."""
    global _KNOWN_CUSTOMER_IDS
    if _KNOWN_CUSTOMER_IDS is None:
        try:
            from pathlib import Path
            with open(Path(__file__).resolve().parent.parent / "data" / "customers.json") as f:
                _KNOWN_CUSTOMER_IDS = {c["customer_id"] for c in json.load(f)}
        except Exception:
            _KNOWN_CUSTOMER_IDS = set()
    return _KNOWN_CUSTOMER_IDS


def validate_customer(customer_id: str) -> None:
    """Raise 400 for empty or unknown customer_id.

    Per CLAUDE.md prime directive #2 -- fail loudly on unexpected
    data instead of returning a slow 200 with empty body.
    """
    from fastapi import HTTPException
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    known = _load_known_customers()
    if known and customer_id not in known:
        raise HTTPException(
            status_code=400,
            detail=f"unknown customer_id: {customer_id!r}",
        )


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

@app.get("/api/demo/today")
def demo_today_endpoint():
    """The demo's frozen 'today'. Frontend uses this for all date math."""
    from src.date_window import demo_today
    return {"date": demo_today().isoformat()}


@app.get("/api/nav/badges")
def nav_badges(customer_id: str = Query(...)):
    """Counts shown on left-nav items.

    Reads from the same precomputed JSON the views use, so the badges
    always agree with the page they link to.
    """
    inv = precomputed.load(customer_id, "invoices_pending") or {}
    match = precomputed.load(customer_id, "matching_pairs") or {}
    anom = precomputed.load(customer_id, "anomalies_scan") or {}

    inv_metrics = inv.get("metrics", {})
    match_metrics = match.get("metrics", {})
    anom_metrics = anom.get("metrics", {})

    return {
        "invoices": inv_metrics.get("review_count", 0),
        "matching": match_metrics.get("unmatched", 0),
        "anomalies": anom_metrics.get("high", 0),
    }


@app.get("/api/health")
def health():
    from src.rate_limit import DEMO_MODE, MAX_REQUESTS
    cached = cache.get("health")
    if cached:
        return cached
    connected = aito.check_connectivity()
    result = {
        "status": "ok",
        "aito_connected": connected,
        "aito_url": config.aito_api_url,
        "demo_mode": DEMO_MODE,
        "rate_limit_per_minute": MAX_REQUESTS,
    }
    cache.set("health", result, ttl=60)
    return result


@app.get("/api/invoices/by_vendor")
def invoices_by_vendor(
    customer_id: str = Query(...),
    vendor: str = Query(...),
    limit: int = 12,
):
    """Recent invoices from one vendor for one customer.

    Drives the "History" tab of the Invoices detail panel — shows
    the user the historical pattern Aito learned from when ranking
    GL codes for this vendor.
    """
    from src.date_window import shift_iso
    try:
        result = aito.search(
            "invoices",
            {"customer_id": customer_id, "vendor": vendor},
            limit=limit,
        )
    except AitoError as exc:
        return {"invoices": [], "error": str(exc)}

    rows = []
    for hit in result.get("hits", []):
        rows.append({
            "invoice_id": hit.get("invoice_id"),
            "invoice_date": shift_iso(hit.get("invoice_date")),
            "amount": hit.get("amount"),
            "category": hit.get("category"),
            "gl_code": hit.get("gl_code"),
            "approver": hit.get("approver"),
            "vat_pct": hit.get("vat_pct"),
        })
    rows.sort(key=lambda r: r.get("invoice_date") or "", reverse=True)
    return {"invoices": rows}


@app.get("/api/invoices/raw")
def invoices_raw(customer_id: str = Query(...), per_page: int = 20):
    """Bare invoice list — no predictions. Fast (~200ms vs ~10s).

    Used to paint the table structure immediately while the heavier
    /api/invoices/pending endpoint computes predictions in the
    background. Progressive rendering: structure first, then values.
    """
    from src.date_window import shift_iso
    try:
        result = aito.search("invoices", {"customer_id": customer_id}, limit=per_page)
    except AitoError as exc:
        return {"invoices": [], "error": str(exc)}

    rows = []
    for hit in result.get("hits", []):
        rows.append({
            "invoice_id": hit.get("invoice_id"),
            "vendor": hit.get("vendor"),
            "amount": hit.get("amount"),
            "invoice_date": shift_iso(hit.get("invoice_date")),
            "due_days": hit.get("due_days"),
            "vat_pct": hit.get("vat_pct"),
            # Placeholder fields so the UI can render rows
            "approver": None,
            "approver_confidence": 0,
            "gl_code": None,
            "gl_label": None,
            "gl_confidence": 0,
            "source": "review",
            "confidence": 0,
            "gl_alternatives": [],
            "approver_alternatives": [],
        })
    return {"invoices": rows}


@app.get("/api/invoices/pending")
def invoices_pending(customer_id: str = Query(...), page: int = 1, per_page: int = 20):
    """Predict GL code and approver for pending invoices.

    Serves data/precomputed/{customer_id}/invoices_pending.json when
    present (hosted demo), falls back to a live Aito compute otherwise
    (dev workflow).
    """
    pre = precomputed.load(customer_id, "invoices_pending")
    if pre is not None:
        data = pre
    else:
        cache_key = f"invoices:{customer_id}"
        data = cache.get(cache_key)
        if data is None:
            with cache.compute_lock(cache_key):
                data = cache.get(cache_key)
                if data is None:
                    try:
                        result = aito.search("invoices", {"customer_id": customer_id}, limit=per_page)
                        sample_invoices = result.get("hits", [])
                    except AitoError:
                        return {"invoices": [], "metrics": {}, "error": "Could not fetch invoices"}

                    rules_key = f"mined_rules:{customer_id}"
                    rules = cache.get(rules_key)
                    if rules is None:
                        with cache.compute_lock(rules_key):
                            rules = cache.get(rules_key)
                            if rules is None:
                                from src.quality_service import mine_rules_for_customer
                                rules = mine_rules_for_customer(aito, customer_id)
                                cache.set(rules_key, rules, ttl=1800)

                    from concurrent.futures import ThreadPoolExecutor
                    from src.invoice_service import predict_invoice
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        predictions = list(pool.map(
                            lambda inv: predict_invoice(aito, {**inv, "customer_id": customer_id}, rules=rules),
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
    pre = precomputed.load(customer_id, "matching_pairs")
    if pre is not None:
        return pre
    cache_key = f"matching:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = match_all(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/rules/drilldown")
def rules_drilldown(
    customer_id: str = Query(...),
    condition_field: str = Query(...),
    condition_value: str = Query(...),
    target_value: str = Query(...),
):
    """Return invoices matching a rule's condition, marked by whether
    they agree with the predicted GL or disagree."""
    where = {"customer_id": customer_id, condition_field: condition_value}
    try:
        result = aito.search("invoices", where, limit=50)
    except AitoError as exc:
        return {"invoices": [], "error": str(exc)}

    from src.date_window import shift_iso
    invoices = []
    for hit in result.get("hits", []):
        invoices.append({
            "invoice_id": hit.get("invoice_id"),
            "vendor": hit.get("vendor"),
            "amount": hit.get("amount"),
            "gl_code": hit.get("gl_code"),
            "category": hit.get("category"),
            "invoice_date": shift_iso(hit.get("invoice_date")),
            "matched_rule": hit.get("gl_code") == target_value,
        })
    # Show disagreeing ones first
    invoices.sort(key=lambda i: (i["matched_rule"], i.get("invoice_date") or ""))
    return {"invoices": invoices}


@app.get("/api/rules/sub_patterns")
def rules_sub_patterns(
    customer_id: str = Query(...),
    condition_field: str = Query(...),
    condition_value: str = Query(...),
    target_field: str = Query("gl_code"),
    target_value: str = Query(...),
):
    """Drill into a discovered rule by relating against secondary inputs.

    Given a top-level rule like `vendor=Telia -> gl_code=6200`, fix
    that conjunction in the where clause and run _relate against
    each remaining input field. Returns the strongest sub-pattern
    per field, e.g.:
        vendor=Telia & gl_code=6200 -> cost_centre=CC-200 (lift 12x)
        vendor=Telia & gl_code=6200 -> approver=Mikael H. (lift 8x)

    Poor-man's "pattern proposition": instead of asking Aito for
    rules whose LHS is a conjunction of anything, we chain _relate
    calls with the discovered conjunction baked into the where.
    """
    SECONDARY_FIELDS = ["category", "cost_centre", "approver", "payment_method", "due_days"]
    base_where = {
        "customer_id": customer_id,
        condition_field: condition_value,
        target_field: target_value,
    }
    rows: list[dict] = []
    for field in SECONDARY_FIELDS:
        if field == condition_field or field == target_field:
            continue
        try:
            r = aito.relate("invoices", base_where, field)
        except AitoError:
            continue
        hits = r.get("hits", [])
        if not hits:
            continue
        top = hits[0]
        related = top.get("related", {}).get(field, {})
        value = related.get("$has")
        if value is None:
            continue
        f_on = int(top.get("fs", {}).get("fOnCondition", 0))
        f_total = int(top.get("fs", {}).get("fCondition", 0))
        lift = float(top.get("lift", 0) or 0)
        if f_on < 3 or lift < 1.5:
            continue
        rows.append({
            "field": field,
            "value": value,
            "support_match": f_on,
            "support_total": f_total,
            "support_ratio": round(f_on / f_total, 2) if f_total else 0,
            "lift": round(lift, 1),
        })

    rows.sort(key=lambda r: (r["lift"], r["support_match"]), reverse=True)
    return {
        "anchor": {
            "condition_field": condition_field,
            "condition_value": condition_value,
            "target_field": target_field,
            "target_value": target_value,
        },
        "sub_patterns": rows[:8],
    }


@app.get("/api/rules/candidates")
def rules_candidates(customer_id: str = Query(...)):
    """Mine rule candidates for a customer."""
    pre = precomputed.load(customer_id, "rules_candidates")
    if pre is not None:
        return pre
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
    pre = precomputed.load(customer_id, "anomalies_scan")
    if pre is not None:
        return pre
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
    pre = precomputed.load(customer_id, "quality_overview")
    if pre is not None:
        return pre
    cache_key = f"quality:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = get_quality_overview(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=300)
    return result


@app.get("/api/quality/audit")
def quality_audit(customer_id: str = Query(...), limit: int = 25):
    """Audit log surfaced from the prediction_log table.

    SOX-style evidence: for every Form Fill submission, did the user
    accept Aito's prediction or override it? Returns aggregate
    accept-rate per field plus the N most recent rows.

    On a fresh deployment prediction_log is empty (no Form Fill
    traffic yet). To keep the demo's audit story visible, we
    synthesize audit rows from the existing tables: each override
    becomes an "overridden" row, each routed invoice a sampled
    "accepted" row. A real production deployment would populate
    prediction_log on every formfill/submit.
    """
    cache_key = f"audit:{customer_id}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        # Pull recent rows for this customer
        recent = aito.search(
            "prediction_log",
            {"customer_id": customer_id},
            limit=200,
        )
    except AitoError as exc:
        return {"error": str(exc), "rows": [], "by_field": {}, "totals": {}}

    hits = sorted(
        recent.get("hits", []),
        key=lambda r: r.get("timestamp", 0),
        reverse=True,
    )

    if not hits:
        # Synthesize from overrides (overridden) + a sample of routed
        # invoices (accepted). Same shape, same fields, just with
        # synthesized=true so the UI can disclose the source.
        try:
            overrides = aito.search("overrides", {"customer_id": customer_id}, limit=80).get("hits", [])
            sample = aito.search(
                "invoices",
                {"customer_id": customer_id, "routed": True, "routed_by": "aito"},
                limit=40,
            ).get("hits", [])
        except AitoError:
            overrides, sample = [], []

        import time as _time
        synth: list[dict] = []
        now = int(_time.time())
        for i, ov in enumerate(overrides):
            synth.append({
                "log_id": ov.get("override_id", f"OV-{i}"),
                "customer_id": customer_id,
                "field": ov.get("field", "gl_code"),
                "predicted_value": ov.get("predicted_value"),
                "user_value": ov.get("corrected_value"),
                "source": "predicted",
                "confidence": float(ov.get("confidence_was", 0) or 0),
                "accepted": False,
                "timestamp": now - 86400 * (i + 1),
                "synthesized": True,
            })
        for i, inv in enumerate(sample):
            for field in ("gl_code", "approver"):
                v = inv.get(field)
                if not v:
                    continue
                synth.append({
                    "log_id": f"INV-{inv.get('invoice_id', i)}-{field}",
                    "customer_id": customer_id,
                    "field": field,
                    "predicted_value": v,
                    "user_value": v,
                    "source": "predicted",
                    "confidence": 0.95,
                    "accepted": True,
                    "timestamp": now - 3600 * (i + 1),
                    "synthesized": True,
                })
        hits = sorted(synth, key=lambda r: r["timestamp"], reverse=True)

    # Aggregate per-field acceptance rate
    by_field: dict[str, dict] = {}
    for r in hits:
        field = r.get("field", "?")
        b = by_field.setdefault(field, {"total": 0, "accepted": 0, "overridden": 0})
        b["total"] += 1
        if r.get("accepted"):
            b["accepted"] += 1
        else:
            b["overridden"] += 1
    for f, b in by_field.items():
        b["accept_rate"] = round(b["accepted"] / b["total"], 3) if b["total"] else 0

    totals = {
        "total": len(hits),
        "accepted": sum(b["accepted"] for b in by_field.values()),
        "overridden": sum(b["overridden"] for b in by_field.values()),
    }
    totals["accept_rate"] = (
        round(totals["accepted"] / totals["total"], 3) if totals["total"] else 0
    )

    result = {
        "rows": hits[:limit],
        "by_field": by_field,
        "totals": totals,
    }
    cache.set(cache_key, result, ttl=120)
    return result


@app.get("/api/quality/evaluations")
def quality_evaluations(customer_id: str = Query(...)):
    """Run Aito _evaluate on every prediction task (parallel)."""
    cache_key = f"evaluations:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    from src.quality_service import compute_evaluations_matrix
    result = compute_evaluations_matrix(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=600)
    return result


@app.get("/api/quality/domains")
def quality_domains():
    """Catalog of evaluable domains, prediction targets, and input fields.

    Drives the Prediction Quality page configurator (mirroring
    aito-demo's EvaluationPage).
    """
    from src.evaluation_service import get_domains_catalog
    return get_domains_catalog()


@app.get("/api/quality/evaluate")
def quality_evaluate(
    customer_id: str = Query(...),
    domain: str = Query(...),
    predict: str = Query(...),
    input_fields: str = Query(...),
    limit: int = 100,
):
    """Run Aito _evaluate for one (domain, predict, inputs) combo.

    input_fields is a comma-separated list of feature names used in
    the where clause via $get bindings. Result has KPIs + per-case
    table + the actual query (so the frontend can display it).

    Cached 10 min per (customer, domain, predict, inputs, limit).
    """
    fields = sorted([f.strip() for f in input_fields.split(",") if f.strip()])
    cache_key = f"eval:{customer_id}:{domain}:{predict}:{','.join(fields)}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    with cache.compute_lock(cache_key):
        cached = cache.get(cache_key)
        if cached:
            return cached
        from src.evaluation_service import run_evaluation
        result = run_evaluation(aito, customer_id, domain, predict, fields, limit=limit)
        if "error" not in result:
            cache.set(cache_key, result, ttl=600)
        return result


@app.get("/api/quality/predictions")
def quality_predictions(customer_id: str = Query(...)):
    """Real prediction accuracy via Aito _evaluate, with rules-only baseline.

    Compares Aito's predictions to ground-truth GL codes on a held-out
    test set, then replays the static rules engine on the same set to
    show the rules-only baseline.
    """
    pre = precomputed.load(customer_id, "prediction_accuracy")
    if pre is not None:
        return pre
    cache_key = f"predictions:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    from src.quality_service import compute_prediction_quality
    result = compute_prediction_quality(aito, customer_id=customer_id)
    cache.set(cache_key, result, ttl=600)
    return result


@app.post("/api/quality/rules/snapshot")
def quality_rules_snapshot(customer_id: str = Query(...)):
    """Write the current mined rule set to the rule_revisions table.

    SOX/audit support: each snapshot is a point-in-time record of the
    rules in effect. Operators run this on a schedule (or before/after
    a control-period close) to build a queryable history.
    """
    from src.quality_service import snapshot_rules_to_revisions
    n = snapshot_rules_to_revisions(aito, customer_id)
    return {"snapshotted": n, "customer_id": customer_id}


@app.get("/api/quality/rules/history")
def quality_rules_history(customer_id: str = Query(...), as_of: int | None = None):
    """Rules in effect at a given timestamp (defaults to now).

    Drives the future "Compare to date" picker in Quality > Rules.
    """
    from src.quality_service import get_rule_history
    return {"rules": get_rule_history(aito, customer_id, as_of=as_of)}


@app.post("/api/quality/rules/backfill")
def quality_rules_backfill(customer_id: str = Query(...)):
    """One-time backfill of 12 weeks of synthesized rule history.

    Real production builds this via a weekly snapshot cron; for the
    demo we call this endpoint once per customer to populate the
    drift charts immediately.
    """
    from src.quality_service import backfill_rule_drift
    n = backfill_rule_drift(aito, customer_id)
    return {"backfilled": n, "customer_id": customer_id}


@app.get("/api/quality/rules/drift")
def quality_rules_drift(customer_id: str = Query(...)):
    """Per-rule precision over the last 12 weeks + weekly override counts.

    Drives the Quality > Rules drift sparklines and the override-trend
    chart that answers "what does this look like at 90 days?"
    """
    cache_key = f"drift:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    from src.quality_service import get_rule_drift_series, get_weekly_override_counts
    result = {
        "rules": get_rule_drift_series(aito, customer_id),
        "weekly_overrides": get_weekly_override_counts(aito, customer_id),
    }
    cache.set(cache_key, result, ttl=600)
    return result


@app.get("/api/quality/rules")
def quality_rules(customer_id: str = Query(...)):
    """Rule performance — replay each static rule against actual GL codes."""
    pre = precomputed.load(customer_id, "rule_performance")
    if pre is not None:
        return pre
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
    except AitoError as exc:
        return {"vendors": [], "error": str(exc)}


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


@app.get("/api/formfill/templates")
def formfill_templates(customer_id: str = Query(...), limit: int = 6):
    """Return the customer's top vendor templates as quick-start cards.

    Mines templates for each of the top-N most-frequent vendors, dropping
    any that don't have a confident template. Used as the landing-page
    'recently used' list in Form Fill so users start from a template
    instead of a blank form.
    """
    from src.formfill_service import predict_template
    from collections import Counter
    cache_key = f"formfill_templates:{customer_id}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        sample = aito.search("invoices", {"customer_id": customer_id}, limit=200)
    except AitoError:
        return {"templates": []}

    vendors = Counter(h["vendor"] for h in sample.get("hits", []) if h.get("vendor"))
    top = [v for v, _ in vendors.most_common(limit * 2)]

    templates = []
    for vendor in top:
        t = predict_template(aito, customer_id, vendor)
        if t:
            templates.append(t)
        if len(templates) >= limit:
            break

    result = {"templates": templates}
    cache.set(cache_key, result, ttl=600)
    return result


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


@app.post("/api/formfill/submit")
def formfill_submit(body: dict):
    """Log a Form Fill submission to prediction_log.

    Each field's (predicted_value, user_value, confidence, source) is
    captured so we can later compute real accuracy: a prediction is
    "correct" if the user accepted it without override.
    """
    import time
    import uuid

    customer_id = body.get("customer_id")
    submissions = body.get("fields", [])
    if not customer_id or not submissions:
        return {"error": "customer_id and fields[] required"}

    now = int(time.time())
    rows = []
    for sub in submissions:
        rows.append({
            "log_id": f"LOG-{uuid.uuid4().hex[:12]}",
            "customer_id": customer_id,
            "field": sub.get("field", ""),
            "predicted_value": sub.get("predicted_value"),
            "user_value": sub.get("user_value"),
            "source": sub.get("source", "user"),
            "confidence": float(sub.get("confidence", 0)),
            "accepted": bool(sub.get("accepted", False)),
            "timestamp": now,
        })

    try:
        # Best-effort batch upload; ignore errors so submit never blocks UX
        aito._request("POST", "/data/prediction_log/batch", json=rows)
        return {"logged": len(rows)}
    except AitoError as exc:
        return {"logged": 0, "error": str(exc)}


@app.get("/api/help/search")
def help_search(
    customer_id: str = Query(...),
    page: str = Query(""),
    q: str = Query(""),
    limit: int = 5,
):
    """Contextual help articles ranked by Aito click-through-rate.

    Same _predict pattern aito-demo uses for product
    recommendations: articles historically clicked in this context
    rise to the top.

    Cached at the server for 10 min per (customer, page, query) tuple.
    The underlying _recommend takes 30+ s under load; the user
    experience is dominated by repeat queries during a session, so
    server-side caching is what makes the drawer responsive.
    """
    cache_key = f"help_search:{customer_id}:{page}:{q}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    from src.help_service import search_help
    articles = search_help(
        aito,
        customer_id=customer_id,
        page=page or None,
        query=q or None,
        limit=limit,
    )
    result = {"articles": articles}
    # Help articles are stable; warmth across a working day matters
    # more than freshness. Bumped 10 min -> 1 hour so the cache
    # survives between drawer interactions.
    cache.set(cache_key, result, ttl=3600)
    return result


@app.post("/api/help/impression")
def help_impression(body: dict):
    """Log that an article was shown (or clicked, if clicked=true)."""
    from src.help_service import log_impression
    log_impression(
        aito,
        article_id=body.get("article_id", ""),
        customer_id=body.get("customer_id", ""),
        page=body.get("page", ""),
        query=body.get("query", ""),
        clicked=bool(body.get("clicked", False)),
        prev_article_id=body.get("prev_article_id") or None,
    )
    return {"ok": True}


def _load_help_related_precompute() -> dict:
    """Read help_related precompute via Aito → bootstrap JSON → empty.

    Sourced from `precompute_store` so a fresh `./do precompute`
    against the live Aito picks up new related-articles without
    rebuilding the container.
    """
    return precompute_store.get("help_related") or {}


@app.get("/api/help/related")
def help_related(
    article_id: str = Query(...),
    customer_id: str = Query(...),
    limit: int = 4,
):
    """Articles users tend to click next from this one.

    Powered by `_recommend WHERE prev_article_id=…, goal: clicked=true`
    against help_impressions. Filtered to the customer's eligibility
    set (global + own internal).

    Cold-path latency on Aito (~5-12s) was bad enough that the first
    click on any expanded help article looked broken in prod. We now
    serve `data/precomputed/help_related.json` when shipped, fall back
    to the in-memory cache, and only as a last resort issue the live
    `_recommend` (1h TTL).
    """
    pre = _load_help_related_precompute()
    cust_pre = pre.get(customer_id, {})
    if article_id in cust_pre:
        return {"articles": cust_pre[article_id][:limit]}

    cache_key = f"help_related:{customer_id}:{article_id}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    from src.help_service import related_articles
    result = {"articles": related_articles(aito, article_id, customer_id, limit=limit)}
    cache.set(cache_key, result, ttl=3600)
    return result


# Computed once at first request from the static fixture, then memoised
# for the process lifetime — invoices.json is ~30MB and reading it
# inside a request handler blocks the event loop for hundreds of ms.
_shared_vendors_full: list[dict] | None = None


@app.get("/api/multitenancy/shared_vendors")
def multitenancy_shared_vendors(limit: int = 8):
    """Vendors used by multiple tenants — the candidate set for the
    'same vendor, different tenants' demo screen.

    Two sources, in order:
    1. landing.json (shipped via git) — the deployed container has
       this even when the raw invoices fixture isn't bundled.
    2. The raw invoices.json fixture, scanned in-process. Available
       in dev / when the fixture is shipped.

    Caches the unbounded list for the process lifetime; callers
    slice to `limit`.
    """
    from src.multitenancy_service import compute_shared_vendors
    global _shared_vendors_full
    if _shared_vendors_full is None:
        # Prefer the precompute store — populated by `./do precompute`,
        # served from Aito with a shipped-JSON bootstrap fallback.
        landing = precompute_store.get("landing")
        if landing and landing.get("vendors"):
            _shared_vendors_full = landing["vendors"]
        else:
            _shared_vendors_full = compute_shared_vendors()
    return {"vendors": _shared_vendors_full[:limit]}


# Local import for the live fallback; keeps the cold path off module
# import time.
from concurrent.futures import ThreadPoolExecutor as _LandingThreadPoolExecutor  # noqa: E402


@app.get("/api/multitenancy/landing")
def multitenancy_landing(vendor_limit: int = 8, tenants_per_vendor: int = 4):
    """One-shot home-page payload: vendors + every tenant template.

    The home page used to fan out (1 shared_vendors call + 4 parallel
    formfill/template calls per vendor) which made first paint visibly
    slow on cold deployments. Precompute writes the same shape to
    data/precomputed/landing.json so production reads it as a static
    file.

    When the JSON is missing (typical for `./do dev` without the
    precompute step), we fall back to computing live so the page
    still works — just slowly.
    """
    pre = precompute_store.get("landing")
    if pre is not None:
        return _slice_landing(pre, vendor_limit, tenants_per_vendor)

    # Live fallback: compute shared vendors + fan out templates.
    # Same shape as the precomputed JSON. Result is *not* written to
    # the precompute store — that's the build pipeline's job.
    from src.multitenancy_service import compute_shared_vendors
    from src.formfill_service import predict_template

    vendors = compute_shared_vendors()[:vendor_limit]
    templates: dict[str, dict] = {}
    with _LandingThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for v in vendors:
            for t in v["tenants"][:tenants_per_vendor]:
                key = f"{v['vendor']}|{t['customer_id']}"
                futures.append((key, pool.submit(
                    predict_template, aito, t["customer_id"], v["vendor"]
                )))
        for key, fut in futures:
            try:
                tpl = fut.result()
                if tpl:
                    templates[key] = tpl
            except Exception:
                pass
    payload = {"vendors": vendors, "templates": templates}
    return _slice_landing(payload, vendor_limit, tenants_per_vendor)


def _slice_landing(payload: dict, vendor_limit: int, tenants_per_vendor: int) -> dict:
    """Trim to the requested limits — kept tiny for cache friendliness."""
    vendors = []
    keep_keys = set()
    for v in (payload.get("vendors") or [])[:vendor_limit]:
        kept = dict(v)
        kept["tenants"] = v["tenants"][:tenants_per_vendor]
        for t in kept["tenants"]:
            keep_keys.add(f"{v['vendor']}|{t['customer_id']}")
        vendors.append(kept)
    templates = {k: v for k, v in (payload.get("templates") or {}).items() if k in keep_keys}
    return {"vendors": vendors, "templates": templates}


@app.get("/api/help/stats")
def help_stats(customer_id: str = Query(...)):
    """Tenant-scoped impression / click / CTR rollup.

    Surfaced in the help drawer so the support-cost lens is visible
    in the demo: the same predictive substrate that fills GL codes
    also ranks help articles, and the CTR number is the deflection
    proxy a CPO actually tracks.
    """
    cache_key = f"help_stats:{customer_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    from src.help_service import customer_help_stats
    result = customer_help_stats(aito, customer_id)
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
