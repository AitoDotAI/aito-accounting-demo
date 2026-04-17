"""Invoice processing service — predictions and rule matching.

Orchestrates the hybrid rules + Aito architecture:
  1. Check if a hardcoded rule matches (high-confidence known patterns)
  2. If no rule, ask Aito to predict GL code and approver
  3. If Aito confidence is below threshold, flag for human review

This simulates what a real accounting SaaS would do. The rules here
are intentionally simple — the point is to show that Aito fills the
gap where rules can't reach.
"""

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError

# Confidence threshold below which invoices go to human review
REVIEW_THRESHOLD = 0.50

# GL code labels for display (a real system would have a chart of accounts)
GL_LABELS = {
    "4100": "COGS",
    "4400": "Supplies",
    "4500": "Office",
    "5100": "Facilities",
    "5200": "Maintenance",
    "6100": "IT & Software",
    "6200": "Telecom",
}


@dataclass
class InvoicePrediction:
    invoice_id: str
    vendor: str
    amount: float
    approver: str | None
    approver_confidence: float
    gl_code: str | None
    gl_label: str | None
    gl_confidence: float
    source: str  # "rule", "aito", or "review"
    confidence: float  # overall confidence (min of GL and approver)

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "amount": self.amount,
            "approver": self.approver,
            "approver_confidence": round(self.approver_confidence, 2),
            "gl_code": self.gl_code,
            "gl_label": self.gl_label,
            "gl_confidence": round(self.gl_confidence, 2),
            "source": self.source,
            "confidence": round(self.confidence, 2),
        }


# ── Simple rules engine ────────────────────────────────────────────
# Each rule returns (gl_code, approver) or None if it doesn't match.
# In production this would be a configurable rules table.

RULES = [
    {
        "name": "Telia → Telecom",
        "match": lambda inv: inv["vendor"] == "Telia Finland",
        "gl_code": "6200",
        "approver": "Mikael H.",
    },
    {
        "name": "Elisa → Telecom",
        "match": lambda inv: inv["vendor"] == "Elisa Oyj",
        "gl_code": "6200",
        "approver": "Mikael H.",
    },
    {
        "name": "Small office purchase",
        "match": lambda inv: inv.get("category") == "office" and inv["amount"] < 50,
        "gl_code": "4500",
        "approver": "Mikael H.",
    },
]


def check_rules(invoice: dict) -> tuple[str, str] | None:
    """Check if any rule matches the invoice.

    Returns (gl_code, approver) if a rule matches, None otherwise.
    """
    for rule in RULES:
        if rule["match"](invoice):
            return rule["gl_code"], rule["approver"]
    return None


def predict_invoice(client: AitoClient, invoice: dict) -> InvoicePrediction:
    """Predict GL code and approver for a single invoice.

    Tries rules first, falls back to Aito, flags for review if
    confidence is too low.
    """
    invoice_id = invoice["invoice_id"]
    vendor = invoice["vendor"]
    amount = invoice["amount"]

    # Step 1: Check rules
    rule_match = check_rules(invoice)
    if rule_match:
        gl_code, approver = rule_match
        return InvoicePrediction(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            approver=f"AP / {approver}",
            approver_confidence=0.99,
            gl_code=gl_code,
            gl_label=GL_LABELS.get(gl_code, gl_code),
            gl_confidence=0.99,
            source="rule",
            confidence=0.99,
        )

    # Step 2: Ask Aito
    where = {"vendor": vendor, "amount": amount}
    if "category" in invoice:
        where["category"] = invoice["category"]

    try:
        gl_result = client.predict("invoices", where, "gl_code")
        approver_result = client.predict("invoices", where, "approver")
    except AitoError:
        # Aito unavailable — flag for review
        return InvoicePrediction(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            approver=None,
            approver_confidence=0.0,
            gl_code=None,
            gl_label=None,
            gl_confidence=0.0,
            source="review",
            confidence=0.0,
        )

    gl_top = gl_result["hits"][0] if gl_result.get("hits") else None
    approver_top = approver_result["hits"][0] if approver_result.get("hits") else None

    gl_code = gl_top["feature"] if gl_top else None
    gl_conf = gl_top["$p"] if gl_top else 0.0
    approver_name = approver_top["feature"] if approver_top else None
    approver_conf = approver_top["$p"] if approver_top else 0.0

    overall_conf = min(gl_conf, approver_conf)

    # Step 3: Classify source
    if overall_conf < REVIEW_THRESHOLD:
        source = "review"
    else:
        source = "aito"

    return InvoicePrediction(
        invoice_id=invoice_id,
        vendor=vendor,
        amount=amount,
        approver=f"AP / {approver_name}" if approver_name else None,
        approver_confidence=approver_conf,
        gl_code=gl_code,
        gl_label=GL_LABELS.get(gl_code, gl_code) if gl_code else None,
        gl_confidence=gl_conf,
        source=source,
        confidence=overall_conf,
    )


def predict_batch(client: AitoClient, invoices: list[dict]) -> list[InvoicePrediction]:
    """Predict GL code and approver for a batch of invoices."""
    return [predict_invoice(client, inv) for inv in invoices]


def compute_metrics(predictions: list[InvoicePrediction]) -> dict:
    """Compute dashboard metrics from a set of predictions."""
    total = len(predictions)
    if total == 0:
        return {"automation_rate": 0, "avg_confidence": 0, "rule_count": 0, "aito_count": 0, "review_count": 0}

    rule_count = sum(1 for p in predictions if p.source == "rule")
    aito_count = sum(1 for p in predictions if p.source == "aito")
    review_count = sum(1 for p in predictions if p.source == "review")
    automated = rule_count + aito_count

    confidences = [p.confidence for p in predictions if p.confidence > 0]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0

    return {
        "automation_rate": round(automated / total, 2),
        "avg_confidence": round(avg_confidence, 2),
        "total": total,
        "rule_count": rule_count,
        "aito_count": aito_count,
        "review_count": review_count,
    }


# Demo invoices — a curated set that showcases different scenarios.
# These would come from a queue in a real system.
DEMO_INVOICES = [
    {"invoice_id": "INV-2841", "vendor": "Kesko Oyj", "amount": 4220.00, "category": "supplies"},
    {"invoice_id": "INV-2842", "vendor": "Telia Finland", "amount": 890.50, "category": "telecom"},
    {"invoice_id": "INV-2843", "vendor": "Hartwall Oy", "amount": 12400.00, "category": "food_bev"},
    {"invoice_id": "INV-2844", "vendor": "Unknown Vendor GmbH", "amount": 3100.00},
    {"invoice_id": "INV-2845", "vendor": "SOK Corporation", "amount": 7850.00, "category": "supplies"},
    {"invoice_id": "INV-2846", "vendor": "Fazer Bakeries", "amount": 2340.00, "category": "food_bev"},
    {"invoice_id": "INV-2847", "vendor": "Verkkokauppa.com", "amount": 1299.00, "category": "it_equipment"},
    {"invoice_id": "INV-2848", "vendor": "ISS Palvelut", "amount": 5200.00, "category": "facilities"},
    {"invoice_id": "INV-2849", "vendor": "Elisa Oyj", "amount": 445.00, "category": "telecom"},
    {"invoice_id": "INV-2850", "vendor": "Kone Oyj", "amount": 18500.00, "category": "maintenance"},
    {"invoice_id": "INV-2851", "vendor": "Lyreco Oy", "amount": 35.00, "category": "office"},
    {"invoice_id": "INV-2852", "vendor": "Wärtsilä Oyj", "amount": 28000.00, "category": "maintenance"},
]
