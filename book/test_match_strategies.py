"""Book tests exploring payment matching strategies.

Compares different approaches to matching bank transactions to invoices:
1. _match via invoice_id link (current schema has the link)
2. _predict vendor_name then find invoice by vendor + amount
3. _predict invoice_id directly (can Aito learn the pairing?)
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


DEMO_TXNS = [
    ("TELIA FINLAND OY", 890.50, "Telia Finland", "INV-2838"),
    ("KESKO OYJ HELSINKI", 4220.00, "Kesko Oyj", "INV-2835"),
    ("SOK CORPORATION", 7852.00, "SOK Corporation", "INV-2839"),
    ("FAZER GROUP OY", 2340.00, "Fazer Bakeries", "INV-2840"),
    ("UNKNOWN TRANSFER", 550.00, None, None),
]


@bt.snapshot_httpx()
def test_strategy_predict_vendor_name(t: bt.TestCaseRun):
    """Strategy 1: _predict vendor_name from description."""
    c = get_client()

    t.h1("Strategy 1: _predict vendor_name")
    t.tln("Predict the vendor from the bank description text.")
    t.tln("This resolves the vendor but not the specific invoice.")
    t.tln("")

    correct = 0
    for desc, amt, expected_vendor, _ in DEMO_TXNS:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": desc},
            "predict": "vendor_name",
            "limit": 1,
        })
        top = result["hits"][0] if result.get("hits") else None
        if top and expected_vendor:
            vendor = top["$value"]
            ok = vendor == expected_vendor
            if ok:
                correct += 1
            t.iln(f"  {desc:25} → {vendor:20} p={top['$p']:.4f}  {'ok' if ok else 'MISS'}")
        elif top:
            t.iln(f"  {desc:25} → {top['$value']:20} p={top['$p']:.4f}  (no expected)")
        else:
            t.iln(f"  {desc:25} → no prediction")

    total = sum(1 for _, _, ev, _ in DEMO_TXNS if ev)
    t.tln("")
    t.tln(f"Vendor accuracy: {correct}/{total}")
    t.tln("Good: resolves vendor name reliably via text tokens.")
    t.tln("Limitation: doesn't identify the specific invoice.")


@bt.snapshot_httpx()
def test_strategy_match_invoice(t: bt.TestCaseRun):
    """Strategy 2: _match to find invoice via link."""
    c = get_client()

    t.h1("Strategy 2: _match via invoice_id link")
    t.tln("Use _match to traverse bank_transactions.invoice_id → invoices")
    t.tln("and find the actual invoice row.")
    t.tln("")

    correct_vendor = 0
    for desc, amt, expected_vendor, expected_inv in DEMO_TXNS:
        result = c.match(
            "bank_transactions",
            {"description": desc, "amount": amt},
            "invoice_id",
            limit=3,
        )
        top = result["hits"][0] if result.get("hits") else None
        if top and expected_vendor:
            vendor = top.get("vendor", "?")
            inv_id = top.get("invoice_id", "?")
            ok = vendor == expected_vendor
            if ok:
                correct_vendor += 1
            t.iln(f"  {desc:25} → {vendor:20} {inv_id:12} p={top['$p']:.4f}  {'ok' if ok else 'MISS'}")
        elif top:
            t.iln(f"  {desc:25} → {top.get('vendor','?'):20} p={top['$p']:.4f}")
        else:
            t.iln(f"  {desc:25} → no match")

    total = sum(1 for _, _, ev, _ in DEMO_TXNS if ev)
    t.tln("")
    t.tln(f"Vendor accuracy: {correct_vendor}/{total}")
    t.tln("_match traverses the link but doesn't use text analysis")
    t.tln("on the description, so common words ('oy') dominate.")


@bt.snapshot_httpx()
def test_strategy_predict_invoice_id(t: bt.TestCaseRun):
    """Strategy 3: _predict invoice_id — returns full invoice rows via link."""
    c = get_client()

    t.h1("Strategy 3: _predict invoice_id via link")
    t.tln("Because bank_transactions.invoice_id links to invoices,")
    t.tln("_predict returns full invoice rows from the linked table.")
    t.tln("This gives vendor, amount, GL code — everything needed to match.")
    t.tln("")

    for desc, amt, expected_vendor, expected_inv in DEMO_TXNS:
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": desc, "amount": amt},
            "predict": "invoice_id",
            "limit": 3,
        })
        hits = result.get("hits", [])
        if hits:
            t.h2(f"{desc}")
            for hit in hits[:3]:
                t.iln(f"  {hit['invoice_id']:12} {hit.get('vendor','?'):20} amt={hit.get('amount',0):>10.2f}  p={hit['$p']:.4f}")
        else:
            t.h2(f"{desc} → no prediction")

    t.tln("")
    t.tln("Key finding: _predict invoice_id returns the right VENDOR's")
    t.tln("invoices via the link. Pick the one with closest amount")
    t.tln("for the final match. Single Aito query, no heuristics.")


@bt.snapshot_httpx()
def test_strategy_hybrid(t: bt.TestCaseRun):
    """Strategy 4: _predict vendor_name + amount proximity."""
    c = get_client()

    t.h1("Strategy 4: Hybrid — _predict vendor + amount ranking")
    t.tln("Step 1: _predict vendor_name from description (text analysis)")
    t.tln("Step 2: Find invoices matching that vendor")
    t.tln("Step 3: Rank by amount proximity")
    t.tln("")
    t.tln("This is the current production approach.")
    t.tln("")

    # Simulate open invoices
    open_invoices = {
        "Telia Finland": [("INV-2838", 890.50)],
        "Kesko Oyj": [("INV-2835", 4220.00)],
        "SOK Corporation": [("INV-2839", 7850.00)],
        "Fazer Bakeries": [("INV-2840", 2340.00)],
    }

    for desc, amt, expected_vendor, expected_inv in DEMO_TXNS:
        # Step 1: predict vendor
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": desc},
            "predict": "vendor_name",
            "limit": 3,
        })

        matched_inv = None
        matched_vendor = None
        best_p = 0

        # Step 2+3: find invoice
        for hit in result.get("hits", []):
            vendor = hit.get("$value")
            p = hit.get("$p", 0)
            if vendor in open_invoices:
                # Pick invoice with closest amount
                for inv_id, inv_amt in open_invoices[vendor]:
                    diff_pct = abs(inv_amt - amt) / max(inv_amt, 1)
                    if diff_pct < 0.05:  # within 5%
                        matched_inv = inv_id
                        matched_vendor = vendor
                        best_p = p
                        break
            if matched_inv:
                break

        if matched_inv:
            ok = matched_inv == expected_inv if expected_inv else "?"
            t.iln(f"  {desc:25} → {matched_vendor:20} {matched_inv:12} p={best_p:.4f}  {'ok' if ok is True else ok}")
        else:
            t.iln(f"  {desc:25} → no match")

    t.tln("")
    t.tln("Hybrid gives best results: text analysis for vendor,")
    t.tln("amount proximity for specific invoice selection.")
