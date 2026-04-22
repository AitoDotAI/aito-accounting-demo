"""Book tests for payment matching — vendor resolution via _predict.

Examines how _predict on the vendor_name Text field resolves bank
transaction descriptions to invoice vendors. Compares with _match
to show why _predict is better for text-based matching.
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


def predict_vendor(client, description):
    """Predict vendor_name from bank description via _predict."""
    return client._request("POST", "/_predict", json={
        "from": "bank_transactions",
        "where": {"description": description},
        "predict": "vendor_name",
        "limit": 5,
    })


@bt.snapshot_httpx()
def test_predict_vendor_resolution(t: bt.TestCaseRun):
    """Resolve bank descriptions to vendors using _predict on vendor_name."""
    c = get_client()

    t.h1("Vendor resolution: _predict on vendor_name")
    t.tln("Bank descriptions are uppercased, abbreviated, and inconsistent.")
    t.tln("_predict on the Text vendor_name field tokenizes the input and")
    t.tln("matches via learned word associations in the training data.")
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
    total = sum(1 for _, exp in test_cases if exp is not None)

    t.h2("Results")
    for desc, expected in test_cases:
        result = predict_vendor(c, desc)
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
            t.iln(f"  {desc:25} -> {vendor:20} p={p:.4f}  [{mark}]")
        else:
            t.iln(f"  {desc:25} -> no prediction")

    t.tln("")
    t.tln(f"Accuracy: {correct}/{total} vendors matched correctly.")
    t.assertln(f"All known vendors matched", correct == total)


@bt.snapshot_httpx()
def test_predict_vendor_with_why(t: bt.TestCaseRun):
    """Show $why explanation for vendor prediction."""
    c = get_client()

    t.h1("$why explanation for vendor matching")
    t.tln("The $why factors show which text tokens drove the prediction.")
    t.tln("")

    result = c._request("POST", "/_predict", json={
        "from": "bank_transactions",
        "where": {"description": "KESKO OYJ HELSINKI"},
        "predict": "vendor_name",
        "select": ["$p", "$value", "$why"],
        "limit": 1,
    })

    top = result["hits"][0]
    t.iln(f"  Description: KESKO OYJ HELSINKI")
    t.iln(f"  Predicted:   {top['$value']}  p={top['$p']:.4f}")
    t.tln("")

    t.h2("$why factors")
    t.icode(json.dumps(top.get("$why", {}), indent=2)[:1200], "json")

    t.tln("")
    t.tln("The description tokens 'kesko' and 'oyj' provide strong lift")
    t.tln("for vendor 'Kesko Oyj' via learned text associations.")


@bt.snapshot_httpx()
def test_predict_vs_match_comparison(t: bt.TestCaseRun):
    """Compare _predict vendor_name vs _match for the same inputs."""
    c = get_client()

    t.h1("Comparison: _predict vs _match for vendor resolution")
    t.tln("_predict on vendor_name uses text tokenization directly.")
    t.tln("_match traverses schema links but doesn't analyze text tokens.")
    t.tln("")

    test_descs = [
        "TELIA FINLAND OY",
        "KESKO OYJ HELSINKI",
        "FAZER GROUP OY",
    ]

    t.h2("Side by side")
    t.iln(f"  {'Description':25} {'_predict':25} {'_match':25}")
    t.iln(f"  {'-'*25} {'-'*25} {'-'*25}")

    for desc in test_descs:
        # _predict
        pr = predict_vendor(c, desc)
        pr_top = pr["hits"][0] if pr.get("hits") else None
        pr_str = f"{pr_top['$value']} p={pr_top['$p']:.4f}" if pr_top else "none"

        # _match
        mr = c.match(
            "bank_transactions",
            {"description": desc, "amount": 1000},
            "invoice_id",
            limit=1,
        )
        mr_top = mr["hits"][0] if mr.get("hits") else None
        mr_str = f"{mr_top.get('vendor', '?')} p={mr_top['$p']:.4f}" if mr_top else "none"

        t.iln(f"  {desc:25} {pr_str:25} {mr_str:25}")

    t.tln("")
    t.tln("_predict gives higher confidence and correct vendor resolution")
    t.tln("because it operates directly on the Text field's token analysis.")
    t.tln("_match relies on historical invoice_id link associations, which")
    t.tln("can be overwhelmed by frequent vendors (like Securitas) in")
    t.tln("sparse training data.")


@bt.snapshot_httpx()
def test_matching_pipeline_with_explanations(t: bt.TestCaseRun):
    """Test the full matching pipeline: vendor resolution + amount + explanations."""
    from src.matching_service import match_bank_txn_to_invoice

    c = get_client()

    t.h1("Full matching pipeline with explanations")
    t.tln("The pipeline: _predict vendor_name → find matching invoices")
    t.tln("→ rank by amount proximity → build explanation.")
    t.tln("")

    test_cases = [
        {"txn_id": "T1", "description": "TELIA FINLAND OY", "amount": 890.50, "bank": "OP"},
        {"txn_id": "T2", "description": "KESKO OYJ HELSINKI", "amount": 4220.00, "bank": "OP"},
        {"txn_id": "T3", "description": "SOK CORPORATION", "amount": 7852.00, "bank": "Nordea"},
    ]

    open_invoices = [
        {"invoice_id": "INV-A", "vendor": "Telia Finland", "amount": 890.50},
        {"invoice_id": "INV-B", "vendor": "Kesko Oyj", "amount": 4220.00},
        {"invoice_id": "INV-C", "vendor": "SOK Corporation", "amount": 7850.00},
    ]

    for txn in test_cases:
        pair = match_bank_txn_to_invoice(c, txn, open_invoices)
        if pair:
            t.h2(f"{txn['description']} → {pair.invoice_vendor}")
            t.iln(f"  status={pair.status}  confidence={pair.confidence:.2f}")
            for e in pair.explanation:
                t.iln(f"  {e['factor']:18} {e['detail']}")
        else:
            t.h2(f"{txn['description']} → no match")
        t.tln("")

    t.tln("Explanation shows: description tokens (lift from Aito $why),")
    t.tln("vendor_name prior, and amount proximity.")
