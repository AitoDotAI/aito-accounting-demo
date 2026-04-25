"""Prediction tests: GL code, approver, and multi-tenant isolation.

Verifies that _predict works correctly with customer_id scoping
and that different customers get different predictions for the
same vendor.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_predict_gl_code(t: bt.TestCaseRun):
    """Predict GL code for invoices within a specific customer."""
    c = get_client()

    t.h1("GL code prediction (per-customer)")
    t.tln("")

    # Get a vendor that this customer uses
    r = c.search("invoices", {"customer_id": "CUST-0000"}, limit=5)
    vendors_seen = set()
    for inv in r["hits"]:
        if inv["vendor"] not in vendors_seen and len(vendors_seen) < 3:
            vendors_seen.add(inv["vendor"])
            result = c.predict("invoices", {"customer_id": "CUST-0000", "vendor": inv["vendor"]}, "gl_code")
            top = result["hits"][0]
            t.iln(f"  {inv['vendor']:35} -> GL {top['feature']:6} p={top['$p']:.4f}")

    t.tln("")
    t.tln("Predictions are scoped to CUST-0000's invoice history.")


@bt.snapshot_httpx()
def test_predict_approver(t: bt.TestCaseRun):
    """Predict approver for invoices within a specific customer."""
    c = get_client()

    t.h1("Approver prediction (per-customer)")
    t.tln("")

    r = c.search("invoices", {"customer_id": "CUST-0000"}, limit=5)
    vendors_seen = set()
    for inv in r["hits"]:
        if inv["vendor"] not in vendors_seen and len(vendors_seen) < 3:
            vendors_seen.add(inv["vendor"])
            result = c.predict("invoices", {"customer_id": "CUST-0000", "vendor": inv["vendor"]}, "approver")
            top = result["hits"][0]
            t.iln(f"  {inv['vendor']:35} -> {top['feature']:20} p={top['$p']:.4f}")


@bt.snapshot_httpx()
def test_multitenant_isolation(t: bt.TestCaseRun):
    """Same vendor, different customers -> different predictions."""
    c = get_client()

    t.h1("Multi-tenant isolation")
    t.tln("Same vendor should predict different GL codes per customer,")
    t.tln("because each customer has their own routing patterns.")
    t.tln("")

    # Find a vendor that appears in multiple customers
    r0 = c.search("invoices", {"customer_id": "CUST-0000"}, limit=1)
    vendor = r0["hits"][0]["vendor"]

    t.h2(f"Vendor: {vendor}")
    customer_ids = ["CUST-0000", "CUST-0003", "CUST-0010", "CUST-0100"]
    for cid in customer_ids:
        result = c.predict("invoices", {"customer_id": cid, "vendor": vendor}, "gl_code")
        top = result["hits"][0]
        count = c.search("invoices", {"customer_id": cid}, limit=0)["total"]
        t.iln(f"  {cid} ({count:>5} invoices): GL {top['feature']:6} p={top['$p']:.4f}")

    t.tln("")
    t.tln("Different GL codes per customer = multi-tenancy working.")


@bt.snapshot_httpx()
def test_cold_start_small_customer(t: bt.TestCaseRun):
    """Prediction quality for a small customer (limited data)."""
    c = get_client()

    t.h1("Cold start: small customer prediction")
    t.tln("Small customers have fewer invoices. How confident is Aito?")
    t.tln("")

    # Find a small customer
    customers = c.search("customers", {"size_tier": "small"}, limit=3)
    for cust in customers["hits"][:3]:
        cid = cust["customer_id"]
        inv_count = c.search("invoices", {"customer_id": cid}, limit=0)["total"]
        inv = c.search("invoices", {"customer_id": cid}, limit=1)["hits"]
        if inv:
            vendor = inv[0]["vendor"]
            result = c.predict("invoices", {"customer_id": cid, "vendor": vendor}, "gl_code")
            top = result["hits"][0]
            t.iln(f"  {cid} ({inv_count:>3} invoices): vendor={vendor[:25]:25} -> GL {top['feature']:6} p={top['$p']:.4f}")

    t.tln("")
    t.tln("Confidence decreases with fewer invoices — honest uncertainty.")
