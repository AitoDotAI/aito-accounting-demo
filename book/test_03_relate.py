"""Rule mining tests: _relate for pattern discovery per customer.

Verifies that _relate finds vendor->GL patterns scoped by customer_id
and that support ratios are meaningful.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_relate_vendor_to_gl(t: bt.TestCaseRun):
    """Find vendor -> GL code patterns for a specific customer."""
    c = get_client()

    t.h1("Rule mining: vendor -> GL code (CUST-0000)")
    t.tln("")

    # Get some vendors for this customer
    r = c.search("invoices", {"customer_id": "CUST-0000"}, limit=20)
    vendors = list({inv["vendor"] for inv in r["hits"]})[:5]

    for vendor in vendors:
        result = c.relate("invoices", {"customer_id": "CUST-0000", "vendor": vendor}, "gl_code")
        top = result["hits"][0]
        gl = top["related"]["gl_code"]["$has"]
        fs = top["fs"]
        f_on = int(fs["fOnCondition"])
        f_cond = int(fs["fCondition"])
        t.iln(f"  {vendor[:35]:35} -> GL {gl}  {f_on}/{f_cond}  lift={top['lift']:.1f}")

    t.tln("")
    t.tln("Support ratios are exact counts from this customer's data.")


@bt.snapshot_httpx()
def test_relate_category_to_gl(t: bt.TestCaseRun):
    """Find category -> GL code patterns for a specific customer."""
    c = get_client()

    t.h1("Rule mining: category -> GL code (CUST-0000)")
    t.tln("")

    categories = ["telecom", "supplies", "facilities", "software", "consulting"]
    for cat in categories:
        result = c.relate("invoices", {"customer_id": "CUST-0000", "category": cat}, "gl_code")
        if result["hits"]:
            top = result["hits"][0]
            gl = top["related"]["gl_code"]["$has"]
            fs = top["fs"]
            f_on = int(fs["fOnCondition"])
            f_cond = int(fs["fCondition"])
            t.iln(f"  {cat:20} -> GL {gl}  {f_on}/{f_cond}")
        else:
            t.iln(f"  {cat:20} -> no data")
