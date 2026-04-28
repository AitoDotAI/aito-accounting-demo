"""Payment matching service — invoice to bank transaction pairing.

Uses Aito _predict on bank_transactions.invoice_id to find matching
invoices. Because invoice_id links to the invoices table, _predict
returns full invoice rows ranked by how well they associate with the
bank transaction's description and amount. The best match among open
invoices is selected by combining Aito's probability with amount
proximity.
"""

from dataclasses import dataclass, field

from src.aito_client import AitoClient, AitoError
from src.invoice_service import _extract_why_factors


@dataclass
class MatchPair:
    invoice_id: str
    invoice_vendor: str
    invoice_amount: float
    bank_txn_id: str | None
    bank_description: str | None
    bank_amount: float | None
    bank_name: str | None
    confidence: float
    status: str  # "matched", "suggested", "unmatched"
    explanation: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "invoice_vendor": self.invoice_vendor,
            "invoice_amount": self.invoice_amount,
            "bank_txn_id": self.bank_txn_id,
            "bank_description": self.bank_description,
            "bank_amount": self.bank_amount,
            "bank_name": self.bank_name,
            "confidence": round(self.confidence, 2),
            "status": self.status,
            "explanation": self.explanation,
        }


def _amount_match_score(invoice_amount: float, bank_amount: float) -> float:
    """Score how close two amounts are. Returns 1.0 for exact, tapering to 0."""
    if invoice_amount == 0:
        return 0.0
    diff_pct = abs(invoice_amount - bank_amount) / invoice_amount
    if diff_pct == 0:
        return 1.0
    if diff_pct <= 0.005:
        return 0.95
    if diff_pct <= 0.02:
        return 0.80
    if diff_pct <= 0.05:
        return 0.50
    return 0.0


def match_bank_txn_to_invoice(
    client: AitoClient,
    txn: dict,
    open_invoices: list[dict],
) -> MatchPair | None:
    """Use Aito _predict invoice_id to match bank transaction to invoice.

    The bank_transactions.invoice_id links to invoices, so _predict
    returns full invoice rows from the linked table, ranked by how
    well they associate with the bank transaction's description and
    amount. We then pick the best match among open invoices.

    Single Aito query — no separate vendor resolution step needed.
    """
    open_ids = {inv["invoice_id"] for inv in open_invoices}
    open_by_id = {inv["invoice_id"]: inv for inv in open_invoices}
    open_by_vendor = {}
    for inv in open_invoices:
        open_by_vendor.setdefault(inv["vendor"], []).append(inv)

    # _predict invoice_id traverses the link and returns invoice rows
    # ranked by association with the bank transaction's features
    try:
        result = client._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {k: v for k, v in [("customer_id", txn.get("customer_id")), ("description", txn["description"]), ("amount", txn["amount"])] if v is not None},
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount", "$why"],
            "limit": 20,
        })
    except AitoError:
        return None

    # Find the best open invoice from Aito's predictions
    best_score = 0.0
    best_invoice = None
    best_p = 0.0
    best_why = None

    for hit in result.get("hits", []):
        inv_id = hit.get("invoice_id")
        vendor = hit.get("vendor")
        aito_p = hit.get("$p", 0)

        # Direct match: Aito returned an open invoice
        if inv_id in open_ids:
            amt_score = _amount_match_score(open_by_id[inv_id]["amount"], txn["amount"])
            combined = aito_p * 0.5 + amt_score * 0.5
            if combined > best_score:
                best_score = combined
                best_invoice = open_by_id[inv_id]
                best_p = aito_p
                best_why = hit.get("$why")
            continue

        # Indirect match: Aito returned the right vendor but different invoice.
        # Check if we have an open invoice from this vendor with matching amount.
        if vendor and vendor in open_by_vendor:
            for inv in open_by_vendor[vendor]:
                amt_score = _amount_match_score(inv["amount"], txn["amount"])
                combined = aito_p * 0.4 + amt_score * 0.6
                if combined > best_score:
                    best_score = combined
                    best_invoice = inv
                    best_p = aito_p
                    best_why = hit.get("$why")

    if best_invoice is None:
        return None

    # Classify confidence
    # _predict vendor_name gives higher $p values than _match, so
    # thresholds can be more meaningful.
    if best_score >= 0.30:
        status = "matched"
    elif best_score >= 0.15:
        status = "suggested"
    else:
        return None

    # Build explanation showing what drove the match
    explanation = _build_explanation(txn, best_invoice, best_p, best_why)

    return MatchPair(
        invoice_id=best_invoice["invoice_id"],
        invoice_vendor=best_invoice["vendor"],
        invoice_amount=best_invoice["amount"],
        bank_txn_id=txn["txn_id"],
        bank_description=txn["description"],
        bank_amount=txn["amount"],
        bank_name=txn["bank"],
        confidence=best_score,
        status=status,
        explanation=explanation,
    )


def _build_explanation(txn: dict, invoice: dict, aito_p: float, aito_why: dict | None = None) -> list[dict]:
    """Build explanation from Aito $why factors + amount proximity."""
    factors = []

    # Aito $why factors — text token lifts and base probability.
    # _extract_why_factors returns the grouped shape:
    #   {type: "base", base_p: 0.46, target_value: ...}
    #   {type: "pattern", lift: 2.0, propositions: [{field, value, highlight?}]}
    if aito_why:
        for wf in _extract_why_factors(aito_why):
            if wf.get("type") == "base":
                base_p = wf.get("base_p", 0)
                factors.append({
                    "factor": "base rate",
                    "detail": f'"{wf.get("target_value", "")}" (prior {base_p:.4f})',
                    "signal": "partial",
                })
            elif wf.get("type") == "pattern":
                lift = float(wf.get("lift", 1) or 1)
                # Cardinality-1 matches in _predict invoice_id produce
                # absurd four-digit lifts (only one invoice has this
                # exact amount/description, so any signal looks "infinitely"
                # more likely). Clamp the displayed value -- the actual
                # contribution is "this is the unique match", not the
                # raw multiplier.
                if lift > 50:
                    detail_lift = "exact match"
                else:
                    detail_lift = f"lift {lift:.1f}x"
                for prop in wf.get("propositions", []):
                    factors.append({
                        "factor": prop["field"],
                        "detail": f'"{prop["value"]}" ({detail_lift})',
                        "signal": "strong" if lift > 2 else "partial",
                    })

    # Amount proximity — Aito's _predict already includes amount in
    # the where clause, so the $why lift on amount surfaces the match
    # quality. Only add a hand-computed factor when amounts disagree
    # enough that the user should question the match (>= 5% off);
    # exact / near-exact would just double-count Aito's own signal.
    diff = abs(invoice["amount"] - txn["amount"])
    if invoice["amount"] > 0 and diff >= invoice["amount"] * 0.05:
        factors.append({
            "factor": "amount",
            "detail": f"differs by {diff:.2f}",
            "signal": "weak",
        })

    return factors


def match_all(client: AitoClient, customer_id: str | None = None) -> dict:
    """Match bank transactions to invoices for a customer."""
    # Fetch bank transactions and open invoices from Aito
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        txn_result = client.search("bank_transactions", where, limit=10)
        inv_result = client.search("invoices", where, limit=20)
    except AitoError:
        return {"pairs": [], "metrics": {"matched": 0, "suggested": 0, "unmatched": 0, "total": 0, "avg_confidence": 0, "match_rate": 0}}

    bank_txns = [{"txn_id": t.get("transaction_id"), "description": t["description"], "amount": t["amount"], "bank": t.get("bank", ""), "customer_id": customer_id} for t in txn_result["hits"]]
    open_invoices = [{"invoice_id": inv["invoice_id"], "vendor": inv["vendor"], "amount": inv["amount"]} for inv in inv_result["hits"]]

    matched_invoices: dict[str, MatchPair] = {}
    remaining = list(open_invoices)

    for txn in bank_txns[:8]:  # limit for response time
        pair = match_bank_txn_to_invoice(client, txn, remaining)
        if pair and pair.invoice_id not in matched_invoices:
            matched_invoices[pair.invoice_id] = pair
            remaining = [inv for inv in remaining if inv["invoice_id"] != pair.invoice_id]

    pairs = list(matched_invoices.values())
    # Add unmatched invoices
    for inv in open_invoices:
        if inv["invoice_id"] not in matched_invoices:
            pairs.append(MatchPair(invoice_id=inv["invoice_id"], invoice_vendor=inv["vendor"], invoice_amount=inv["amount"], bank_txn_id=None, bank_description=None, bank_amount=None, bank_name=None, confidence=0.0, status="unmatched"))
            if len(pairs) >= 20:
                break

    matched = sum(1 for p in pairs if p.status == "matched")
    suggested = sum(1 for p in pairs if p.status == "suggested")
    unmatched = sum(1 for p in pairs if p.status == "unmatched")
    confidences = [p.confidence for p in pairs if p.confidence > 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "pairs": [p.to_dict() for p in pairs],
        "metrics": {
            "matched": matched,
            "suggested": suggested,
            "unmatched": unmatched,
            "total": len(pairs),
            "avg_confidence": round(avg_conf, 2),
            "match_rate": round((matched + suggested) / len(pairs), 2) if pairs else 0,
        },
    }
