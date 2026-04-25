"""Payment matching tests: _predict invoice_id via schema link.

Verifies that bank transaction descriptions can be matched to
invoices through the invoice_id link, scoped by customer_id.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_predict_invoice_from_bank_txn(t: bt.TestCaseRun):
    """Match bank transactions to invoices via _predict invoice_id."""
    c = get_client()

    t.h1("Payment matching: _predict invoice_id")
    t.tln("Bank transaction -> invoice via schema link traversal.")
    t.tln("")

    # Get some bank transactions for CUST-0000
    r = c.search("bank_transactions", {"customer_id": "CUST-0000"}, limit=5)

    for txn in r["hits"][:5]:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {
                "customer_id": "CUST-0000",
                "description": txn["description"],
                "amount": txn["amount"],
            },
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount"],
            "limit": 1,
        })
        if result["hits"]:
            top = result["hits"][0]
            t.iln(f"  {txn['description'][:25]:25} €{txn['amount']:>10,.2f}  ->  {top.get('vendor','?')[:20]:20} p={top['$p']:.4f}")
        else:
            t.iln(f"  {txn['description'][:25]:25} -> no match")

    t.tln("")
    t.tln("Matches scoped to CUST-0000 via customer_id in where clause.")


@bt.snapshot_httpx()
def test_predict_vendor_name(t: bt.TestCaseRun):
    """Vendor resolution from bank description text."""
    c = get_client()

    t.h1("Vendor resolution: _predict vendor_name")
    t.tln("")

    r = c.search("bank_transactions", {"customer_id": "CUST-0000"}, limit=5)
    for txn in r["hits"][:5]:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {
                "customer_id": "CUST-0000",
                "description": txn["description"],
            },
            "predict": "vendor_name",
            "limit": 1,
        })
        if result["hits"]:
            top = result["hits"][0]
            expected = txn.get("vendor_name", "?")
            predicted = top["$value"]
            ok = "ok" if predicted == expected else "MISS"
            t.iln(f"  {txn['description'][:25]:25} -> {predicted[:25]:25} [{ok}]")
