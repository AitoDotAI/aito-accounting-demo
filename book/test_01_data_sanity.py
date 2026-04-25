"""Sanity checks: verify data is loaded correctly in Aito.

Run after ./do load-data to confirm all tables exist, have expected
record counts, and the schema links work.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_table_counts(t: bt.TestCaseRun):
    """Verify all tables exist and have records."""
    c = get_client()

    t.h1("Table record counts")
    t.tln("")

    tables = ["customers", "corporate_entities", "employees", "invoices", "bank_transactions", "overrides"]
    for table in tables:
        r = c.search(table, {}, limit=0)
        t.iln(f"  {table:25} {r['total']:>8,} records")

    t.tln("")
    t.assertln("invoices table has records", c.search("invoices", {}, limit=0)["total"] > 0)
    t.assertln("customers table has records", c.search("customers", {}, limit=0)["total"] > 0)


@bt.snapshot_httpx()
def test_customer_distribution(t: bt.TestCaseRun):
    """Check customer size distribution — geometric series."""
    c = get_client()

    t.h1("Customer size distribution")
    t.tln("")

    r = c.search("customers", {}, limit=300)
    customers = r["hits"]

    by_tier = {}
    for cust in customers:
        tier = cust["size_tier"]
        by_tier.setdefault(tier, []).append(cust)

    for tier in ["enterprise", "large", "midmarket", "small"]:
        custs = by_tier.get(tier, [])
        total_inv = sum(c["invoice_count"] for c in custs)
        t.iln(f"  {tier:12} {len(custs):4} customers, {total_inv:>10,} planned invoices")


@bt.snapshot_httpx()
def test_sample_invoices(t: bt.TestCaseRun):
    """Show sample invoices from different customers."""
    c = get_client()

    t.h1("Sample invoices")
    t.tln("")

    # Get invoices from a large and small customer
    for cid in ["CUST-0000", "CUST-0254"]:
        r = c.search("invoices", {"customer_id": cid}, limit=3)
        t.h2(f"Customer {cid} ({r['total']} invoices)")
        for inv in r["hits"][:3]:
            t.iln(f"  {inv['vendor']:35} €{inv['amount']:>10,.2f}  GL={inv['gl_code']}  {inv['description'][:40]}")
        t.tln("")


@bt.snapshot_httpx()
def test_schema_links(t: bt.TestCaseRun):
    """Verify schema links are set up correctly."""
    c = get_client()

    t.h1("Schema links")
    t.tln("")

    schema = c.get_schema()["schema"]
    for table_name, tdef in schema.items():
        links = []
        for col, cdef in tdef.get("columns", {}).items():
            if "link" in cdef:
                links.append(f"{col} -> {cdef['link']}")
        if links:
            t.iln(f"  {table_name}:")
            for link in links:
                t.iln(f"    {link}")

    t.tln("")
    t.assertln("invoices.customer_id links to customers",
               "link" in schema["invoices"]["columns"]["customer_id"])
