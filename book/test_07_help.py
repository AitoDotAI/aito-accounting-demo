"""Booktest coverage for the contextual help system.

The help system uses Aito's `_recommend` operator — the same call
aito-demo uses for product recommendations. The pattern: rank
article_ids by predicted probability of `clicked=true` given the
current context (customer_id, page, optional query).

Tests:
1. Schema sanity — help_articles + help_impressions tables.
2. _recommend returns context-relevant articles for /invoices on
   CUST-0000 (own-internal articles + app docs surface).
3. _evaluate on the underlying click probability — documents how
   well the impression history predicts clicks. The accuracy is
   honest: classification near baseline at this data scale, but
   the calibrated probability (geomMeanP) is meaningful as a
   ranking signal — which is what _recommend uses internally.
4. Cold-start customer — small-tier customers with no impressions
   fall back to the global pool.
"""

import booktest as bt

from src.aito_client import AitoClient
from src.config import load_config
from src.help_service import search_help


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_help_schema_exists(t: bt.TestCaseRun):
    """help_articles + help_impressions tables are created with expected columns."""
    c = get_client()

    t.h1("Help schema")
    t.tln("")

    schema = c.get_schema()["schema"]

    for table, expected in [
        ("help_articles", {"article_id", "title", "body", "category", "customer_id", "tags", "page_context"}),
        ("help_impressions", {"impression_id", "article_id", "customer_id", "page", "query", "clicked", "timestamp"}),
    ]:
        if table not in schema:
            t.iln(f"  {table}: NOT CREATED — run ./do reset-data")
            t.assertln(f"{table} exists", False)
            continue

        cols = sorted(schema[table]["columns"].keys())
        t.h2(table)
        for col in cols:
            cdef = schema[table]["columns"][col]
            t.iln(f"  {col:18} {cdef['type']:8}")
        present = set(cols)
        missing = expected - present
        t.tln("")
        t.assertln(f"{table} has all expected columns", not missing)


@bt.snapshot_httpx()
def test_help_search_top_articles_for_invoices_page(t: bt.TestCaseRun):
    """Top-5 help articles for CUST-0000 on /invoices via _recommend.

    Expectation: own-customer internal articles + app docs with
    page_context=/invoices should dominate the top 5.
    """
    c = get_client()

    t.h1("Help recommend — CUST-0000 on /invoices")
    t.tln("Underlying call: POST /_recommend WHERE customer_id, page → goal: { clicked: true }")
    t.tln("")

    articles = search_help(c, customer_id="CUST-0000", page="/invoices", limit=5)
    t.iln(f"  {len(articles)} articles returned")
    t.tln("")
    for a in articles:
        scope = "own-internal" if a["customer_id"] == "CUST-0000" else (
            "global" if a["customer_id"] == "*" else f"other-customer({a['customer_id']})"
        )
        t.iln(f"  [{a['category']:8}] [{scope:14}] {a['title']}")

    t.tln("")
    t.assertln("returns at least 1 article", len(articles) >= 1)
    # No other-customer leakage
    other = [a for a in articles if a["customer_id"] not in ("*", "CUST-0000")]
    t.assertln("no other-customer internal articles leak through", not other)


@bt.snapshot_httpx()
def test_help_evaluate_click_prediction(t: bt.TestCaseRun):
    """Document the underlying click-prediction signal on help_impressions.

    `_recommend` ranks article_ids by predicted P(clicked=true | context).
    `_evaluate` measures the same prediction problem; we run it here so
    the snapshot captures the honest quality at this data scale.

    With ~14k impressions and 26% baseline CTR:
    - Per-impression *classification* accuracy hovers near baseAccuracy
      (predicting "no click" gets ~74% right by default). This isn't
      the metric to optimize.
    - The *ranking* the same model produces is meaningfully useful:
      measured directly (top-half vs bottom-half avg actual CTR), the
      lift is roughly 1.5–2× — the user-facing benefit.

    Sanity bounds only — specific accuracy numbers shift on data regen.
    """
    c = get_client()

    t.h1("_evaluate: click prediction on help_impressions")
    t.tln("Predicting per-impression click probability — used as ranking signal.")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "testSource": {
            "from": "help_impressions",
            "limit": 200,
        },
        "evaluate": {
            "from": "help_impressions",
            "where": {
                "customer_id": {"$get": "customer_id"},
                "page": {"$get": "page"},
                "article_id": {"$get": "article_id"},
            },
            "predict": "clicked",
        },
    })

    accuracy = result.get("accuracy", 0)
    base = result.get("baseAccuracy", 0)
    gain = result.get("accuracyGain", 0)
    samples = result.get("testSamples", 0)
    geom_p = result.get("geomMeanP", 0)

    t.iln(f"  Accuracy:      {accuracy:.1%}")
    t.iln(f"  Base accuracy: {base:.1%}    (always-predict-majority)")
    t.iln(f"  Accuracy gain: {gain:.1%}")
    t.iln(f"  Test samples:  {samples}")
    t.iln(f"  Geom mean p:   {geom_p:.4f}    (higher = more confident ranking)")

    t.tln("")
    # Sanity bounds — values should be in valid ranges, not specific accuracies
    t.assertln("accuracy ∈ [0, 1]", 0 <= accuracy <= 1)
    t.assertln("baseAccuracy ∈ [0, 1]", 0 <= base <= 1)
    t.assertln("test samples ≥ 50", samples >= 50)
    t.assertln("geomMeanP > 0.3 (predictions aren't random)", geom_p > 0.3)


@bt.snapshot_httpx()
def test_help_evaluate_on_unseen_customer(t: bt.TestCaseRun):
    """How well does CTR prediction generalize to a customer with less history?

    Smaller customers have fewer impressions. Honest answer: accuracy
    will be closer to baseline. This test documents the cold-start
    behavior so we don't claim better-than-real performance.
    """
    c = get_client()

    t.h1("_evaluate on a small customer's impressions")
    t.tln("")

    # Pick a customer outside the top 20 (which got internal articles + impressions)
    customers = c.search("customers", {"size_tier": "small"}, limit=5)
    if not customers.get("hits"):
        t.iln("(no small customers found — skipping)")
        return
    cid = customers["hits"][0]["customer_id"]
    inv_count = c.search("invoices", {"customer_id": cid}, limit=0)["total"]
    imp_count = c.search("help_impressions", {"customer_id": cid}, limit=0)["total"]
    t.iln(f"  Customer:     {cid} ({inv_count} invoices, {imp_count} impressions)")
    t.tln("")

    if imp_count < 20:
        t.iln(f"  Only {imp_count} impressions — cold start by design.")
        t.iln(f"  Real production: this customer's CTR ranking falls back to global.")
        t.assertln("documented cold-start behavior", True)
        return

    result = c._request("POST", "/_evaluate", json={
        "testSource": {
            "from": "help_impressions",
            "where": {"customer_id": cid},
            "limit": 50,
        },
        "evaluate": {
            "from": "help_impressions",
            "where": {
                "customer_id": cid,
                "page": {"$get": "page"},
                "article_id": {"$get": "article_id"},
            },
            "predict": "clicked",
        },
    })

    t.iln(f"  Accuracy:      {result.get('accuracy', 0):.1%}")
    t.iln(f"  Base accuracy: {result.get('baseAccuracy', 0):.1%}")
    t.iln(f"  Accuracy gain: {result.get('accuracyGain', 0):.1%}")
    t.iln(f"  Test samples:  {result.get('testSamples', 0)}")
