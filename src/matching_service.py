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


# Demo invoices waiting to be matched
DEMO_OPEN_INVOICES = [
    {"invoice_id": "INV-2838", "vendor": "Telia Finland", "amount": 890.50},
    {"invoice_id": "INV-2835", "vendor": "Kesko Oyj", "amount": 4220.00},
    {"invoice_id": "INV-2839", "vendor": "SOK Corporation", "amount": 7850.00},
    {"invoice_id": "INV-2844", "vendor": "Unknown Vendor GmbH", "amount": 3100.00},
    {"invoice_id": "INV-2840", "vendor": "Fazer Bakeries", "amount": 2340.00},
    {"invoice_id": "INV-2836", "vendor": "Verkkokauppa.com", "amount": 1299.00},
]

# Demo bank transactions to match against
DEMO_BANK_TXNS = [
    {"txn_id": "TXN-20001", "description": "TELIA FINLAND OY", "amount": 890.50, "bank": "OP Bank"},
    {"txn_id": "TXN-20002", "description": "KESKO OYJ HELSINKI", "amount": 4220.00, "bank": "OP Bank"},
    {"txn_id": "TXN-20003", "description": "SOK CORPORATION", "amount": 7852.00, "bank": "Nordea"},
    {"txn_id": "TXN-20004", "description": "VENDOR GMBH BERLIN", "amount": 3099.00, "bank": "SEPA"},
    {"txn_id": "TXN-20005", "description": "FAZER GROUP OY", "amount": 2340.00, "bank": "Nordea"},
    {"txn_id": "TXN-20006", "description": "UNKNOWN TRANSFER", "amount": 550.00, "bank": "OP Bank"},
]


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
    returns full invoice rows from the linked table, ranked by Aito's
    probability. We trust Aito's ranking and pick the first open
    invoice from the results.

    No amount heuristic — Aito handles the full ranking. If we wanted
    to narrow the search space (e.g. only open invoices, or filter by
    amount range), we could add where conditions on the invoice side.
    """
    open_ids = {inv["invoice_id"] for inv in open_invoices}
    open_by_vendor = {}
    for inv in open_invoices:
        open_by_vendor.setdefault(inv["vendor"], []).append(inv)

    # _predict invoice_id traverses the link and returns invoice rows
    # ranked by association with the bank transaction's features.
    # Aito considers description text tokens and amount together.
    try:
        result = client._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": {"description": txn["description"], "amount": txn["amount"]},
            "predict": "invoice_id",
            "select": ["$p", "invoice_id", "vendor", "amount", "$why"],
            "limit": 20,
        })
    except AitoError:
        return None

    # Pick the first result that matches an open invoice — either
    # directly by invoice_id, or by vendor (Aito may return a
    # different invoice from the same vendor).
    best_invoice = None
    best_p = 0.0
    best_why = None

    for hit in result.get("hits", []):
        inv_id = hit.get("invoice_id")
        vendor = hit.get("vendor")
        aito_p = hit.get("$p", 0)

        # Direct match: Aito returned an open invoice
        if inv_id in open_ids:
            best_invoice = next(i for i in open_invoices if i["invoice_id"] == inv_id)
            best_p = aito_p
            best_why = hit.get("$why")
            break

        # Vendor match: same vendor, pick best open invoice for that vendor
        if vendor and vendor in open_by_vendor:
            best_invoice = open_by_vendor[vendor][0]
            best_p = aito_p
            best_why = hit.get("$why")
            break

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

    # Aito $why factors — text token lifts and base probability
    if aito_why:
        why_factors = _extract_why_factors(aito_why)
        for wf in why_factors:
            is_base = wf.get("type") == "base"
            if is_base:
                factors.append({
                    "factor": wf["field"],
                    "detail": f'"{wf["value"]}" (prior {wf["lift"]:.4f})',
                    "signal": "partial",
                })
            else:
                factors.append({
                    "factor": wf["field"],
                    "detail": f'"{wf["value"]}" (lift {wf["lift"]}x)',
                    "signal": "strong" if wf["lift"] > 2 else "partial",
                })

    # Amount proximity — computed outside Aito since _predict on
    # vendor_name within bank_transactions doesn't cross-reference
    # invoice amounts. Amount matching narrows which invoice for a
    # given vendor.
    diff = abs(invoice["amount"] - txn["amount"])
    if diff == 0:
        factors.append({"factor": "amount", "detail": f"exact match ({txn['amount']})", "signal": "strong"})
    elif diff < invoice["amount"] * 0.005:
        factors.append({"factor": "amount", "detail": f"within 0.5% (diff {diff:.2f})", "signal": "strong"})
    elif diff < invoice["amount"] * 0.02:
        factors.append({"factor": "amount", "detail": f"within 2% (diff {diff:.2f})", "signal": "partial"})
    elif diff < invoice["amount"] * 0.05:
        factors.append({"factor": "amount", "detail": f"within 5% (diff {diff:.2f})", "signal": "partial"})
    else:
        factors.append({"factor": "amount", "detail": f"differs by {diff:.2f}", "signal": "weak"})

    return factors


def match_all(client: AitoClient) -> dict:
    """Run matching for all demo invoice/bank transaction pairs."""
    matched_invoices: dict[str, MatchPair] = {}
    used_txns: set[str] = set()

    # For each bank transaction, find the best matching open invoice
    remaining_invoices = list(DEMO_OPEN_INVOICES)

    for txn in DEMO_BANK_TXNS:
        pair = match_bank_txn_to_invoice(client, txn, remaining_invoices)
        if pair and pair.invoice_id not in matched_invoices:
            matched_invoices[pair.invoice_id] = pair
            used_txns.add(txn["txn_id"])
            remaining_invoices = [
                inv for inv in remaining_invoices
                if inv["invoice_id"] != pair.invoice_id
            ]

    # Build final pairs list in invoice order
    pairs = []
    for inv in DEMO_OPEN_INVOICES:
        if inv["invoice_id"] in matched_invoices:
            pairs.append(matched_invoices[inv["invoice_id"]])
        else:
            pairs.append(MatchPair(
                invoice_id=inv["invoice_id"],
                invoice_vendor=inv["vendor"],
                invoice_amount=inv["amount"],
                bank_txn_id=None,
                bank_description=None,
                bank_amount=None,
                bank_name=None,
                confidence=0.0,
                status="unmatched",
            ))

    matched = sum(1 for p in pairs if p.status == "matched")
    suggested = sum(1 for p in pairs if p.status == "suggested")
    unmatched = sum(1 for p in pairs if p.status == "unmatched")
    confidences = [p.confidence for p in pairs if p.confidence > 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "pairs": [p.to_dict() for p in pairs],
        "unmatched_txns": [
            {"txn_id": t["txn_id"], "description": t["description"],
             "amount": t["amount"], "bank": t["bank"]}
            for t in DEMO_BANK_TXNS if t["txn_id"] not in used_txns
        ],
        "metrics": {
            "matched": matched,
            "suggested": suggested,
            "unmatched": unmatched,
            "total": len(pairs),
            "avg_confidence": round(avg_conf, 2),
            "match_rate": round((matched + suggested) / len(pairs), 2) if pairs else 0,
        },
    }
