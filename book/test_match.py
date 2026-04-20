"""Book tests for Aito _match — invoice to bank transaction matching.

Examines how _match traverses schema links to find invoices related
to bank transaction descriptions and amounts.
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_match_known_vendor(t: bt.TestCaseRun):
    """Match a bank transaction to invoices via schema link."""
    c = get_client()

    t.h1("_match: KESKO OYJ HELSINKI → invoices")
    t.tln("Aito's _match traverses bank_transactions.invoice_id → invoices")
    t.tln("and returns full invoice rows ranked by association strength.")
    t.tln("")

    result = c.match(
        table="bank_transactions",
        where={"description": "KESKO OYJ HELSINKI", "amount": 4220},
        match_field="invoice_id",
        limit=5,
    )

    t.h2("Top matches")
    for hit in result["hits"][:5]:
        t.iln(f"  {hit['invoice_id']:12} vendor={hit['vendor']:20} amount={hit['amount']:>10.2f}  p={hit['$p']:.4f}")

    t.tln("")
    top = result["hits"][0]
    t.assertln("Top match is Kesko Oyj", top["vendor"] == "Kesko Oyj")
    t.tln("")
    t.tln(f"Note: $p={top['$p']:.4f} is low in absolute terms because")
    t.tln(f"probability is spread across {result['total']} invoices.")


@bt.snapshot_httpx()
def test_match_various_descriptions(t: bt.TestCaseRun):
    """Match different bank descriptions to see vendor resolution."""
    c = get_client()

    t.h1("_match: vendor resolution from bank descriptions")
    t.tln("Bank descriptions are uppercased, abbreviated, and inconsistent.")
    t.tln("_match handles the text similarity via the schema link.")
    t.tln("")

    test_cases = [
        ("TELIA FINLAND OY", 890.50, "Telia Finland"),
        ("KESKO OYJ HELSINKI", 4220.00, "Kesko Oyj"),
        ("SOK CORPORATION", 7852.00, "SOK Corporation"),
        ("FAZER GROUP OY", 2340.00, "Fazer Bakeries"),
        ("UNKNOWN TRANSFER", 550.00, None),
    ]

    for desc, amount, expected_vendor in test_cases:
        result = c.match(
            table="bank_transactions",
            where={"description": desc, "amount": amount},
            match_field="invoice_id",
            limit=3,
        )
        top = result["hits"][0] if result["hits"] else None
        if top:
            vendor = top["vendor"]
            correct = vendor == expected_vendor if expected_vendor else "?"
            mark = "ok" if correct is True else ("expected" if expected_vendor is None else "MISS")
            t.iln(f"  {desc:25} → {vendor:20} p={top['$p']:.4f}  [{mark}]")
        else:
            t.iln(f"  {desc:25} → no match")

    t.tln("")
    t.tln("_match traverses schema links and finds associated records.")
    t.tln("Some vendors may not match due to sparse training data.")


@bt.snapshot_httpx()
def test_predict_vendor_name(t: bt.TestCaseRun):
    """Use _predict on vendor_name field for better text matching."""
    import httpx as _httpx
    c = get_client()

    t.h1("_predict vendor_name from bank description")
    t.tln("The vendor_name Text field enables Aito to tokenize and match")
    t.tln("bank descriptions like 'KESKO OYJ HELSINKI' to vendor 'Kesko Oyj'.")
    t.tln("This is more reliable than _match for vendor resolution.")
    t.tln("")

    test_cases = [
        ("TELIA FINLAND OY", "Telia Finland"),
        ("KESKO OYJ HELSINKI", "Kesko Oyj"),
        ("SOK CORPORATION", "SOK Corporation"),
        ("FAZER GROUP OY", "Fazer Bakeries"),
        ("VERKKOKAUPPA.COM", "Verkkokauppa.com"),
        ("KONE", "Kone Oyj"),
        ("ISS PALVELUT", "ISS Palvelut"),
        ("UNKNOWN TRANSFER", None),
    ]

    correct = 0
    total = len([t for _, exp in test_cases if exp is not None])

    for desc, expected in test_cases:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": desc},
            "predict": "vendor_name",
            "limit": 3,
        })
        top = result["hits"][0] if result.get("hits") else None
        if top:
            vendor = top["$value"]
            p = top["$p"]
            if expected:
                ok = vendor == expected
                if ok:
                    correct += 1
                mark = "ok" if ok else "MISS"
            else:
                mark = f"low-p" if p < 0.05 else "unexpected"
            t.iln(f"  {desc:25} → {vendor:20} p={p:.4f}  [{mark}]")
        else:
            t.iln(f"  {desc:25} → no prediction")

    t.tln("")
    t.tln(f"Accuracy: {correct}/{total} vendors matched correctly.")
    t.tln("")
    t.tln("_predict on the Text vendor_name field uses token analysis to")
    t.tln("match partial and case-insensitive descriptions reliably.")
