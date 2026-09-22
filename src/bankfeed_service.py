"""Code bank lines that settle no invoice.

Payment Matching answers "which outstanding invoice does this payment
settle?" and assumes one exists. A real bank feed is full of lines where
none does — bank charges, card settlements, direct debits, tax, payroll —
and somebody codes those by hand.

This is the other half of that page: for a line with no invoice, predict
the GL code from what this tenant did with similar lines before. See
ADR 0024.
"""

from dataclasses import dataclass, field

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS, _extract_why_factors

# Below this, the view asks for a human instead of asserting a code. Coding
# is an accounting entry, not a suggestion — a wrong code that looks
# confident is worse than an honest "needs review".
REVIEW_THRESHOLD = 0.55


@dataclass
class CodedLine:
    txn_id: str
    description: str
    amount: float
    bank: str
    gl_code: str
    gl_label: str
    confidence: float
    status: str  # "coded" | "needs_review"
    explanation: list[dict] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "txn_id": self.txn_id,
            "description": self.description,
            "amount": self.amount,
            "bank": self.bank,
            "gl_code": self.gl_code,
            "gl_label": self.gl_label,
            "confidence": round(self.confidence, 2),
            "status": self.status,
            "explanation": self.explanation,
            "alternatives": self.alternatives,
        }


def code_bank_line(client: AitoClient, txn: dict) -> CodedLine | None:
    """Predict the GL code for one statement line.

    `amount_band` is passed alongside `amount` deliberately. Aito will not
    condition on a raw Decimal, so without the band the prediction falls
    back to the counterparty's most common code and ignores the size
    entirely: a card settlement came back 4100 at both EUR 120 and EUR
    4800, where the truth flips at the small/medium boundary. With the
    band, the same counterparty codes 4500 when small and 4100 when not.
    """
    where = {
        "customer_id": txn["customer_id"],
        "description": txn["description"],
        "amount": txn["amount"],
    }
    if txn.get("amount_band"):
        where["amount_band"] = txn["amount_band"]

    try:
        result = client._request("POST", "/_query", json={
            "from": "bank_transactions",
            "where": where,
            "predict": "gl_code",
            "select": [
                "$value",
                "$p",
                {"$why": {"highlight": {"posPreTag": "<mark>", "posPostTag": "</mark>"}}},
            ],
            # Enough to cover the tenant's GL vocabulary; a short limit
            # silently drops alternatives rather than erroring.
            "limit": 12,
        })
    except AitoError:
        return None

    hits = result.get("hits") or []
    if not hits:
        return None
    top = hits[0]
    p = float(top.get("$p", 0) or 0)
    code = str(top.get("$value", ""))

    return CodedLine(
        txn_id=txn["txn_id"],
        description=txn["description"],
        amount=txn["amount"],
        bank=txn.get("bank", ""),
        gl_code=code,
        gl_label=GL_LABELS.get(code, code),
        confidence=p,
        status="coded" if p >= REVIEW_THRESHOLD else "needs_review",
        explanation=list(_extract_why_factors(top.get("$why"))),
        alternatives=[
            {"gl_code": str(h.get("$value", "")),
             "gl_label": GL_LABELS.get(str(h.get("$value", "")), str(h.get("$value", ""))),
             "p": round(float(h.get("$p", 0) or 0), 4)}
            for h in hits[1:4]
        ],
    )


def code_all(client: AitoClient, customer_id: str, limit: int = 8) -> dict:
    """Every un-coded line in this tenant's feed, with a proposed code.

    Selects on `invoice_id` being absent rather than filtering after the
    fetch: a line that settles an invoice belongs to Payment Matching, and
    pulling it in here would put the same row on two pages answering two
    different questions.
    """
    try:
        rows = client.search(
            "bank_transactions",
            {"customer_id": customer_id, "invoice_id": None},
            limit=limit,
        ).get("hits", [])
    except AitoError:
        return {"lines": [], "metrics": _metrics([])}

    lines: list[CodedLine] = []
    for row in rows:
        coded = code_bank_line(client, {
            "txn_id": row.get("transaction_id"),
            "customer_id": customer_id,
            "description": row["description"],
            "amount": row["amount"],
            "amount_band": row.get("amount_band"),
            "bank": row.get("bank", ""),
        })
        if coded is not None:
            lines.append(coded)

    return {"lines": [ln.to_dict() for ln in lines], "metrics": _metrics(lines)}


def _metrics(lines: list[CodedLine]) -> dict:
    total = len(lines)
    coded = sum(1 for ln in lines if ln.status == "coded")
    avg = sum(ln.confidence for ln in lines) / total if total else 0.0
    return {
        "total": total,
        "coded": coded,
        "needs_review": total - coded,
        "avg_confidence": round(avg, 2),
        "automation_rate": round(coded / total, 2) if total else 0,
    }
