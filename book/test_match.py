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
    t.tln("Note: With only ~120 bank transactions, some vendors have too few")
    t.tln("historical pairings for _match to learn the association reliably.")
    t.tln("More training data (a few hundred transactions) would improve")
    t.tln("accuracy for underrepresented vendors like Telia (6 txns) vs")
    t.tln("Securitas (17 txns) which dominates due to frequency.")
