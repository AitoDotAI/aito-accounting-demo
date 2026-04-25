"""Book tests for payment matching with amount filtering.

Explores using invoice_id.amount.$gte/$lte in the where clause
to narrow _predict invoice_id results by amount range.
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


DEMO_TXNS = [
    ("TELIA FINLAND OY", 890.50, "Telia Finland"),
    ("KESKO OYJ HELSINKI", 4220.00, "Kesko Oyj"),
    ("SOK CORPORATION", 7852.00, "SOK Corporation"),
    ("FAZER GROUP OY", 2340.00, "Fazer Bakeries"),
    ("UNKNOWN TRANSFER", 550.00, None),
]


@bt.snapshot_httpx()
def test_predict_invoice_no_amount_filter(t: bt.TestCaseRun):
    """Baseline: _predict invoice_id without amount filtering."""
    c = get_client()

    t.h1("Baseline: _predict invoice_id (no amount filter)")
    t.tln("")

    for desc, amt, expected in DEMO_TXNS:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": desc, "amount": amt},
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount"],
            "limit": 3,
        })
        hits = result.get("hits", [])
        t.h2(f"{desc} (€{amt})")
        for hit in hits[:3]:
            match = "ok" if expected and hit.get("vendor") == expected else ""
            t.iln(f"  {hit['invoice_id']:12} {hit.get('vendor','?'):20} €{hit.get('amount',0):>10.2f}  p={hit['$p']:.4f}  {match}")
        t.tln("")


@bt.snapshot_httpx()
def test_predict_invoice_amount_filter_50pct(t: bt.TestCaseRun):
    """_predict invoice_id with 50% amount range filter."""
    c = get_client()

    t.h1("_predict invoice_id with amount filter (±50%)")
    t.tln("")

    for desc, amt, expected in DEMO_TXNS:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {
                "description": desc,
                "amount": amt,
                "invoice_id": {
                    "amount": {"$gte": amt * 0.50, "$lte": amt * 1.50},
                },
            },
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount"],
            "limit": 3,
        })
        hits = result.get("hits", [])
        t.h2(f"{desc} (€{amt})")
        if hits:
            for hit in hits[:3]:
                match = "ok" if expected and hit.get("vendor") == expected else ""
                t.iln(f"  {hit['invoice_id']:12} {hit.get('vendor','?'):20} €{hit.get('amount',0):>10.2f}  p={hit['$p']:.4f}  {match}")
        else:
            t.iln("  no results")
        t.tln("")


@bt.snapshot_httpx()
def test_predict_invoice_amount_filter_10pct(t: bt.TestCaseRun):
    """_predict invoice_id with 10% amount range filter."""
    c = get_client()

    t.h1("_predict invoice_id with amount filter (±10%)")
    t.tln("")

    for desc, amt, expected in DEMO_TXNS:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {
                "description": desc,
                "amount": amt,
                "invoice_id": {
                    "amount": {"$gte": amt * 0.90, "$lte": amt * 1.10},
                },
            },
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount"],
            "limit": 3,
        })
        hits = result.get("hits", [])
        t.h2(f"{desc} (€{amt})")
        if hits:
            for hit in hits[:3]:
                match = "ok" if expected and hit.get("vendor") == expected else ""
                t.iln(f"  {hit['invoice_id']:12} {hit.get('vendor','?'):20} €{hit.get('amount',0):>10.2f}  p={hit['$p']:.4f}  {match}")
        else:
            t.iln("  no results")
        t.tln("")


@bt.snapshot_httpx()
def test_predict_invoice_with_why(t: bt.TestCaseRun):
    """Check if amount appears in $why when filtering by amount."""
    c = get_client()

    t.h1("$why with amount filter — does amount show as factor?")
    t.tln("")

    desc, amt = "KESKO OYJ HELSINKI", 4220.0
    result = c._request("POST", "/_predict", json={
        "from": "bank_transactions",
        "where": {
            "description": desc,
            "amount": amt,
            "invoice_id": {
                "amount": {"$gte": amt * 0.50, "$lte": amt * 1.50},
            },
        },
        "predict": "invoice_id",
        "select": ["$p", "invoice_id", "vendor", "amount", "$why"],
        "limit": 1,
    })

    top = result["hits"][0]
    t.iln(f"  {top['invoice_id']:12} {top.get('vendor','?'):20} €{top.get('amount',0):>10.2f}  p={top['$p']:.4f}")
    t.tln("")

    t.h2("$why factors")
    t.icode(json.dumps(top.get("$why", {}), indent=2)[:1500], "json")
