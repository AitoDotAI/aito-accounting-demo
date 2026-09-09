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
    # Aito's own $p for this invoice, distinct from `confidence`, which
    # blends it with amount proximity. The panel needs both: the factor
    # chain is a decomposition of THIS number, not of the blend.
    model_p: float = 0.0

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
            "model_p": self.model_p,
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
    # ranked by association with the bank transaction's features.
    # $why with `highlight` returns the matched description tokens
    # already wrapped in <mark> tags (Aito's text analyzer marks
    # whichever spans of the bank description carried the signal).
    # `customer_id` in `where` is EVIDENCE about the transaction; it does not
    # restrict which invoices Aito may rank. Without the linked-path scope the
    # candidate universe is every invoice in the instance, so a CUST-0002
    # payment gets ranked against CUST-0000's invoices -- measured at 17
    # foreign candidates in the top 5 over 8 payments. `invoice_id.customer_id`
    # scopes the candidate domain through the link instead, which is the
    # tenant boundary this page needs. It also happens to cut latency ~6x and
    # the probability's under-confidence ~48x, but the boundary is the reason.
    #
    # `vendor_name` rides on the bank transaction and was not being passed.
    # Four of five wrong assignments in a 640-invoice evaluation picked an
    # invoice from the WRONG VENDOR while the description named the right
    # one, so the field the bank already gives us was the missing evidence.
    customer_id = txn.get("customer_id")
    where = {"description": txn["description"], "amount": txn["amount"]}
    if customer_id is not None:
        where["customer_id"] = customer_id
        where["invoice_id.customer_id"] = customer_id
    if txn.get("vendor_name"):
        where["vendor_name"] = txn["vendor_name"]

    try:
        result = client._request("POST", "/_predict", json={
            "from": "bank_transactions",
            "where": where,
            "predict": "invoice_id",
            "select": [
                "$p",
                "invoice_id",
                "vendor",
                "amount",
                {"$why": {"highlight": {"posPreTag": "<mark>", "posPostTag": "</mark>"}}},
            ],
            # 20, not 5. The old limit was set when highlight on a Text
            # field made 20 candidates run >120 s. Re-measured warm on
            # 2.8.1 against the tenant-scoped candidate domain, limit 5
            # and limit 20 are both ~5.2 s -- the limit costs nothing now,
            # and 5 was truncating the true invoice out of the ranking.
            "limit": 20,
        })
    except AitoError:
        return None

    # Direct hits and same-vendor substitutes are scored SEPARATELY, and a
    # direct hit always wins.
    #
    # They used to compete on one number, with the substitute weighting
    # amount 0.6 against a direct hit's 0.5. Because Aito's $p for a link
    # target is ~1e-3 while an amount score is ~1, the amount term decided
    # everything -- and a substitute from the wrong vendor with a marginally
    # closer amount beat the invoice Aito had ranked FIRST:
    #
    #   direct    INV-000146 Pukaron   0.00116*0.5 + 0.95*0.5 = 0.4756
    #   substitute INV-000171 Kardex   0.00015*0.4 + 0.95*0.6 = 0.5701  won
    #
    # Aito was right and the arithmetic threw it away. A substitute is a
    # fallback for when Aito ranked nothing we hold, never an improvement
    # on something it did.
    best_direct: tuple[float, dict, float, dict | None] | None = None
    best_sub: tuple[float, dict, float, str] | None = None

    for hit in result.get("hits", []):
        inv_id = hit.get("invoice_id")
        vendor = hit.get("vendor")
        aito_p = hit.get("$p", 0)

        # Direct match: Aito returned an open invoice.
        if inv_id in open_ids:
            amt_score = _amount_match_score(open_by_id[inv_id]["amount"], txn["amount"])
            combined = aito_p * 0.5 + amt_score * 0.5
            if best_direct is None or combined > best_direct[0]:
                best_direct = (combined, open_by_id[inv_id], aito_p, hit.get("$why"))
            continue

        # Indirect: Aito ranked a different invoice from the same vendor, so
        # we substitute an open one from that vendor whose amount fits.
        #
        # Aito's `$why` explains the invoice Aito ranked, NOT the one we
        # substitute, so it must not be carried over -- doing so rendered one
        # invoice's explanation under another invoice's match, with the base
        # rate naming an id that appeared nowhere on screen.
        # `_build_explanation` describes the substitution instead.
        if vendor and vendor in open_by_vendor:
            for inv in open_by_vendor[vendor]:
                amt_score = _amount_match_score(inv["amount"], txn["amount"])
                combined = aito_p * 0.4 + amt_score * 0.6
                if best_sub is None or combined > best_sub[0]:
                    best_sub = (combined, inv, aito_p, inv_id)

    best_ranked_id: str | None = None
    if best_direct is not None:
        best_score, best_invoice, best_p, best_why = best_direct
    elif best_sub is not None:
        best_score, best_invoice, best_p, best_ranked_id = best_sub
        best_why = None
    else:
        best_score, best_invoice, best_p, best_why = 0.0, None, 0.0, None

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
    explanation = _build_explanation(txn, best_invoice, best_p, best_why, best_ranked_id)

    return MatchPair(
        invoice_id=best_invoice["invoice_id"],
        invoice_vendor=best_invoice["vendor"],
        invoice_amount=best_invoice["amount"],
        bank_txn_id=txn["txn_id"],
        bank_description=txn["description"],
        bank_amount=txn["amount"],
        bank_name=txn["bank"],
        confidence=best_score,
        model_p=best_p,
        status=status,
        explanation=explanation,
    )


def _build_explanation(
    txn: dict,
    invoice: dict,
    aito_p: float,
    aito_why: dict | None = None,
    ranked_invoice_id: str | None = None,
) -> list[dict]:
    """Pass through Aito $why factors in the grouped shape so the
    matching page can render the same WhyCards UI as Invoice
    Processing -- pattern cards with text-token highlights and lift
    multipliers.

    On top of that we append a synthetic "amount" factor only when the
    txn and invoice amounts disagree by >= 5% (worth flagging as a
    warning); exact/near-exact amounts would double-count Aito's own
    $why on the amount field.

    `ranked_invoice_id` is set when this match is a same-vendor
    SUBSTITUTE: Aito ranked that invoice, we are pairing a different one
    because its amount fits better. There is no Aito `$why` for the
    invoice we chose, so we state the substitution rather than borrowing
    the explanation of the invoice Aito did rank — which is a different
    invoice, and reads as gibberish under this one.
    """
    factors: list[dict] = list(_extract_why_factors(aito_why)) if aito_why else []

    if ranked_invoice_id is not None:
        factors.append({
            "type": "pattern",
            "lift": 1.0,
            "propositions": [
                {"field": "vendor", "value": invoice["vendor"]},
                {"field": "matched via", "value":
                    f"same vendor — Aito ranked {ranked_invoice_id}, "
                    f"this invoice's amount fits the payment better"},
            ],
            "highlights": [],
        })

    # Big-disagreement warning. Modelled as a pattern card with a
    # single proposition and lift = 1.0 noted in propositions[0].value
    # so the renderer can display it consistently.
    diff = abs(invoice["amount"] - txn["amount"])
    if invoice["amount"] > 0 and diff >= invoice["amount"] * 0.05:
        factors.append({
            "type": "pattern",
            "lift": 0.5,  # negative-signal flag: cuts confidence
            "propositions": [{"field": "amount", "value": f"differs by {diff:.2f}"}],
            "highlights": [],
        })

    return factors


def match_all(
    client: AitoClient,
    customer_id: str | None = None,
    payment_count: int = 8,
    ledger_decoys: int = 30,
) -> dict:
    """Assign each incoming payment to an invoice in the open ledger.

    The direction matters and used to be backwards. A payment arrives and
    has to be assigned to an invoice; an invoice with no payment is simply
    unpaid, which is not a failure. Previously this fetched some payments
    and some *unrelated* invoices, matched what it could, and then listed
    every leftover invoice as "unmatched" — so a working matcher reported
    "5 matched, 15 unmatched" and read as 25% accurate. Those 15 invoices
    were never anyone's payment target; their payments had not been
    fetched at all.

    Now the ledger is built to contain the fetched payments' own invoices
    plus decoys, and only payments can be unmatched.

    Building the ledger uses `bank_transactions.invoice_id`, the fixture's
    ground-truth link, purely to decide WHICH invoices are outstanding —
    a real deployment reads that from its AP ledger instead. The matcher
    itself never sees the link: it gets `description` and `amount` only,
    and has to re-derive the pairing.
    """
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        txn_result = client.search("bank_transactions", where, limit=payment_count)
        payments = txn_result.get("hits", [])
        if not payments:
            raise AitoError("no bank transactions for this customer")

        # The invoices these payments settle — the ledger must contain
        # them, or the task is unanswerable rather than hard.
        target_ids = sorted({t["invoice_id"] for t in payments if t.get("invoice_id")})
        target_rows = client.search(
            "invoices", {**where, "invoice_id": {"$or": target_ids}}, limit=len(target_ids),
        ).get("hits", []) if target_ids else []

        # Decoys, so choosing the right invoice is a real discrimination.
        decoy_rows = client.search("invoices", where, limit=ledger_decoys).get("hits", [])
    except AitoError:
        return {"pairs": [], "metrics": {"matched": 0, "suggested": 0, "unmatched": 0,
                                         "total": 0, "avg_confidence": 0, "match_rate": 0}}

    ledger: dict[str, dict] = {}
    for row in target_rows + decoy_rows:
        ledger.setdefault(row["invoice_id"], {
            "invoice_id": row["invoice_id"],
            "vendor": row["vendor"],
            "amount": row["amount"],
        })

    bank_txns = [{
        "txn_id": t.get("transaction_id"),
        "description": t["description"],
        "amount": t["amount"],
        "bank": t.get("bank", ""),
        "customer_id": customer_id,
    } for t in payments]

    pairs: list[MatchPair] = []
    remaining = list(ledger.values())
    for txn in bank_txns:
        pair = match_bank_txn_to_invoice(client, txn, remaining)
        if pair is not None:
            pairs.append(pair)
            # One invoice settles one payment.
            remaining = [inv for inv in remaining if inv["invoice_id"] != pair.invoice_id]
        else:
            pairs.append(MatchPair(
                invoice_id="", invoice_vendor="", invoice_amount=0.0,
                bank_txn_id=txn["txn_id"], bank_description=txn["description"],
                bank_amount=txn["amount"], bank_name=txn["bank"],
                confidence=0.0, status="unmatched",
            ))

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
            "ledger_size": len(ledger),
            "avg_confidence": round(avg_conf, 2),
            "match_rate": round((matched + suggested) / len(pairs), 2) if pairs else 0,
        },
    }
