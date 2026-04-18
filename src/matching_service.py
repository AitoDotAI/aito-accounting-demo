"""Payment matching service — invoice to bank transaction pairing.

Uses Aito's _match endpoint to find invoices related to bank
transactions. The _match query traverses the link between
bank_transactions.invoice_id → invoices.invoice_id and returns
full invoice rows ranked by match probability.

Amount proximity is used as a secondary signal to pick the best
invoice when Aito returns multiple vendor matches.
"""

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError


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
    """Use Aito _match to find the best invoice for a bank transaction.

    Aito's _match traverses the bank_transactions → invoices link and
    returns invoice rows ranked by how well they associate with the
    bank transaction's features (description text, amount).

    We then pick the best match among open invoices by combining
    Aito's $p score with amount proximity.
    """
    open_ids = {inv["invoice_id"] for inv in open_invoices}
    open_by_vendor = {}
    for inv in open_invoices:
        open_by_vendor.setdefault(inv["vendor"], []).append(inv)

    try:
        result = client.match(
            table="bank_transactions",
            where={"description": txn["description"], "amount": txn["amount"]},
            match_field="invoice_id",
            limit=20,
        )
    except AitoError:
        return None

    # Find the best open invoice from Aito's matches
    best_score = 0.0
    best_invoice = None
    best_p = 0.0

    for hit in result.get("hits", []):
        vendor = hit.get("vendor")
        aito_p = hit.get("$p", 0)

        # Check if any open invoice matches this vendor
        matching_invoices = open_by_vendor.get(vendor, [])
        for inv in matching_invoices:
            amt_score = _amount_match_score(inv["amount"], txn["amount"])
            # Combine Aito probability with amount score
            combined = aito_p * 0.6 + amt_score * 0.4
            if combined > best_score:
                best_score = combined
                best_invoice = inv
                best_p = aito_p

    if best_invoice is None:
        return None

    # Classify confidence
    # Note: Aito _match $p values are spread across all invoices, so
    # even a strong match may have $p ~0.19. The combined score accounts
    # for this by weighting amount proximity heavily.
    if best_score >= 0.30:
        status = "matched"
    elif best_score >= 0.15:
        status = "suggested"
    else:
        return None

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
    )


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
