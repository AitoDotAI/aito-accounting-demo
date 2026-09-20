"""Payment matching tests: _predict invoice_id via schema link.

Verifies that bank transaction descriptions can be matched to
invoices through the invoice_id link, scoped by customer_id.
"""

import booktest as bt

from book.aito_env import get_client


@bt.snapshot_httpx()
def test_predict_invoice_from_bank_txn(t: bt.TestCaseRun):
    """Match bank transactions to invoices via _predict invoice_id."""
    c = get_client()

    t.h1("Payment matching: _predict invoice_id")
    t.tln("Bank transaction -> invoice via schema link traversal.")
    t.tln("")
    t.tln("The candidate domain is the OPEN LEDGER, not every invoice the")
    t.tln("tenant has. Ranking all ~2000 makes the true invoice compete with")
    t.tln("rows that were never outstanding, and it loses whenever the payment")
    t.tln("quotes no reference number. Both shapes are shown below.")
    t.tln("")

    # Get some bank transactions for CUST-0000
    r = c.search("bank_transactions", {"customer_id": "CUST-0000"}, limit=5)
    txns = r["hits"][:5]

    # The open ledger: the invoices these payments settle, plus decoys, so
    # picking the right one is a real discrimination. A deployment reads
    # this from its AP ledger; here the fixture link supplies it.
    ledger_ids = sorted({t_["invoice_id"] for t_ in txns if t_.get("invoice_id")})
    decoys = c.search("invoices", {"customer_id": "CUST-0000"}, limit=25)["hits"]
    ledger_ids = sorted(set(ledger_ids) | {d["invoice_id"] for d in decoys})

    def top_match(txn: dict, scoped: bool) -> dict | None:
        where = {
            "customer_id": "CUST-0000",
            "description": txn["description"],
            "amount": txn["amount"],
        }
        if scoped:
            # The linked key, not the bare target. `$or` on the predict
            # target itself ranks correctly but returns `invoice_id: null`
            # on every hit after the first.
            where["invoice_id.invoice_id"] = {"$or": ledger_ids}
        result = c._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": where,
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount"],
            "limit": 1,
        })
        return result["hits"][0] if result["hits"] else None

    t.h2("Unscoped — ranks every invoice the tenant has")
    for txn in txns:
        top = top_match(txn, scoped=False)
        line = f"{top.get('vendor','?')[:20]:20} p={top['$p']:.4f}" if top else "no match"
        t.iln(f"  {txn['description'][:25]:25} €{txn['amount']:>10,.2f}  ->  {line}")

    t.tln("")
    t.h2("Scoped to the open ledger")
    for txn in txns:
        top = top_match(txn, scoped=True)
        line = f"{top.get('vendor','?')[:20]:20} p={top['$p']:.4f}" if top else "no match"
        correct = " [ok]" if top and top.get("invoice_id") == txn.get("invoice_id") else ""
        t.iln(f"  {txn['description'][:25]:25} €{txn['amount']:>10,.2f}  ->  {line}{correct}")

    t.tln("")
    t.tln("Scoping raises $p by orders of magnitude, because the probability")
    t.tln("is now spread over the invoices that could actually be settled.")


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
