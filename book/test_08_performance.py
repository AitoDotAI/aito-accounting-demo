"""Latency snapshots for the operators that drive the demo.

Each query is wrapped in `t.imsln(lambda: ...)` which prints the
elapsed milliseconds as info (so the snapshot diff doesn't break on
timing variance) and returns the result. Open the latest run's
snapshot under `books/` to see how each operator scales with the
dataset and the customer's size tier.

Run with:
    ./do book                    # snapshot diff, fail if behaviour
                                 # changed (response shape, hit count)
    uv run python -m booktest -p book/test_08_performance.py
                                 # interactive review with latencies
"""

import booktest as bt
from src.aito_client import AitoClient
from src.config import load_config


def get_client():
    return AitoClient(load_config())


def _hit_top(result):
    hits = result.get("hits", [])
    return hits[0] if hits else None


@bt.snapshot_httpx()
def test_search_latency_by_tier(t: bt.TestCaseRun):
    """How does _search scale with the customer's invoice count?"""
    c = get_client()
    t.h1("_search latency by customer tier")
    t.tln("")

    # One customer per tier — pick deterministic ids
    cases = [
        ("CUST-0000", "enterprise (16K invoices)"),
        ("CUST-0003", "large (4K invoices)"),
        ("CUST-0015", "midmarket (1K invoices)"),
        ("CUST-0100", "small (250 invoices)"),
        ("CUST-0254", "small (125 invoices)"),
    ]

    for cid, label in cases:
        t.h2(f"{cid} — {label}")
        r = t.imsln(lambda: c.search("invoices", {"customer_id": cid}, limit=20))
        t.iln(f"  total={r['total']}  hits returned={len(r['hits'])}")
        t.tln(f"  total > 0: {r['total'] > 0}")
        t.tln("")


@bt.snapshot_httpx()
def test_predict_latency(t: bt.TestCaseRun):
    """_predict latency for the canonical invoice → GL code flow."""
    c = get_client()
    t.h1("_predict latency: invoice → GL code")
    t.tln("")

    # Pick three vendors from the enterprise customer
    sample = c.search("invoices", {"customer_id": "CUST-0000"}, limit=10)
    vendors = []
    seen = set()
    for h in sample["hits"]:
        if h["vendor"] not in seen and len(seen) < 3:
            vendors.append(h["vendor"])
            seen.add(h["vendor"])

    for vendor in vendors:
        t.h2(f"vendor = {vendor}")
        r = t.imsln(lambda v=vendor: c.predict(
            "invoices",
            {"customer_id": "CUST-0000", "vendor": v},
            "gl_code",
        ))
        top = _hit_top(r)
        if top is not None:
            t.tln(f"  top GL: {top['feature']}  p > 0: {top['$p'] > 0}")
        t.tln("")


@bt.snapshot_httpx()
def test_predict_latency_cold_vs_warm(t: bt.TestCaseRun):
    """Same query twice in a row: Aito's own caching warms up."""
    c = get_client()
    t.h1("_predict cold vs warm (same query twice)")
    t.tln("First call hits cold Aito state; second runs after the")
    t.tln("index is in memory. The gap shows Aito-side caching.")
    t.tln("")

    sample = c.search("invoices", {"customer_id": "CUST-0000"}, limit=1)
    vendor = sample["hits"][0]["vendor"]

    t.h2(f"vendor = {vendor}")

    t.iln("first call:")
    r1 = t.imsln(lambda: c.predict(
        "invoices",
        {"customer_id": "CUST-0000", "vendor": vendor},
        "gl_code",
    ))
    t.iln("second call:")
    r2 = t.imsln(lambda: c.predict(
        "invoices",
        {"customer_id": "CUST-0000", "vendor": vendor},
        "gl_code",
    ))

    t1 = _hit_top(r1)
    t2 = _hit_top(r2)
    t.tln(f"  same top GL: {t1['feature'] == t2['feature']}")


@bt.snapshot_httpx()
def test_relate_latency(t: bt.TestCaseRun):
    """_relate latency for vendor → gl_code rule mining."""
    c = get_client()
    t.h1("_relate latency: vendor → gl_code")
    t.tln("This is the slow operator -- it returns the discovered")
    t.tln("association rules between fields.")
    t.tln("")

    cases = [
        ("CUST-0000", "enterprise"),
        ("CUST-0015", "midmarket"),
    ]

    for cid, label in cases:
        t.h2(f"{cid} — {label}")
        # Discover what gl_code values relate to a fixed condition.
        # The dual call (relate vendor, condition by gl_code) would also
        # work; this shape mirrors what compute_rule_performance uses.
        r = t.imsln(lambda c_id=cid: c.relate(
            "invoices",
            {"customer_id": c_id, "category": "telecom"},
            "gl_code",
        ))
        rules = r.get("hits", [])
        t.iln(f"  rules returned: {len(rules)}")
        if rules:
            top = rules[0]
            t.iln(f"  top related gl_code lift={top.get('lift', 0):.2f}")
        t.tln(f"  rules > 0: {len(rules) > 0}")
        t.tln("")


@bt.snapshot_httpx()
def test_evaluate_latency(t: bt.TestCaseRun):
    """_evaluate latency for the GL accuracy view."""
    c = get_client()
    t.h1("_evaluate latency: gl_code accuracy")
    t.tln("This drives /quality/predictions. It runs leave-one-out")
    t.tln("cross-validation on the testSource sample.")
    t.tln("")

    t.h2("CUST-0000 — sample size 50")
    r = t.imsln(lambda: c._request("POST", "/_evaluate", json={
        "testSource": {
            "from": "invoices",
            "where": {"customer_id": "CUST-0000"},
            "limit": 50,
        },
        "evaluate": {
            "from": "invoices",
            "where": {
                "customer_id": "CUST-0000",
                "vendor": {"$get": "vendor"},
                "amount": {"$get": "amount"},
                "category": {"$get": "category"},
            },
            "predict": "gl_code",
        },
    }))
    t.iln(f"  accuracy={r.get('accuracy', 0):.3f}  baseline={r.get('baseAccuracy', 0):.3f}"
          f"  testSamples={r.get('testSamples', 0)}")
    t.tln(f"  accuracy beats baseline: {r.get('accuracy', 0) > r.get('baseAccuracy', 0)}")
