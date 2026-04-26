"""Invoice processing service — predictions and rule matching.

Orchestrates the hybrid rules + Aito architecture:
  1. Check if a hardcoded rule matches (high-confidence known patterns)
  2. If no rule, ask Aito to predict GL code and approver
  3. If Aito confidence is below threshold, flag for human review

Returns top-3 alternatives with $why explanations for each prediction,
so the UI can show dropdown alternatives and explain why Aito chose
each value.
"""

from dataclasses import dataclass, field

from src.aito_client import AitoClient, AitoError

REVIEW_THRESHOLD = 0.50

GL_LABELS = {
    "4100": "COGS",
    "4400": "Supplies",
    "4500": "Office",
    "5100": "Facilities",
    "5200": "Maintenance",
    "6100": "IT & Software",
    "6200": "Telecom",
}


def _extract_alternatives(hits: list[dict], label_map: dict | None = None, prefix: str = "") -> list[dict]:
    """Extract top-3 alternatives from Aito _predict hits.

    Each alternative includes the value, display label, confidence,
    and $why explanation factors.
    """
    alts = []
    for hit in hits[:3]:
        value = hit.get("feature", "")
        display = value
        if label_map and value in label_map:
            display = f"{value} \u2013 {label_map[value]}"
        if prefix:
            display = f"{prefix}{display}"

        why_factors = _extract_why_factors(hit.get("$why"))

        alts.append({
            "value": value,
            "display": display,
            "confidence": round(hit.get("$p", 0), 4),
            "why": why_factors,
        })
    return alts


def _extract_why_factors(why: dict | None) -> list[dict]:
    """Extract human-readable factors from Aito $why structure.

    Aito $why is nested: {type: "product", factors: [...]} where each
    factor may be a lift on a proposition like {vendor: {$has: "Kesko"}}.
    We flatten this into a simple list of {field, value, lift} entries.
    """
    if not why or not isinstance(why, dict):
        return []

    factors = []
    _walk_why(why, factors)
    # Sort by lift descending, take top 5
    factors.sort(key=lambda f: abs(f.get("lift", 0)), reverse=True)
    return factors[:5]


def _walk_why(node: dict, factors: list[dict]) -> None:
    """Recursively walk the $why tree to find proposition lifts."""
    if node.get("type") == "relatedPropositionLift":
        prop = node.get("proposition", {})
        lift = node.get("value", 0)
        _extract_propositions(prop, lift, factors)
    if node.get("type") == "baseP":
        # Base probability — useful context
        prop = node.get("proposition", {})
        base_p = node.get("value", 0)
        for field_name, condition in prop.items():
            if isinstance(condition, dict) and "$has" in condition:
                factors.append({
                    "field": field_name,
                    "value": str(condition["$has"]),
                    "lift": round(base_p, 4),
                    "type": "base",
                })
    for child in node.get("factors", []):
        if isinstance(child, dict):
            _walk_why(child, factors)


def _extract_propositions(prop: dict, lift: float, factors: list[dict]) -> None:
    """Extract field/value pairs from a proposition, handling $and arrays."""
    if "$and" in prop:
        for sub_prop in prop["$and"]:
            _extract_propositions(sub_prop, lift, factors)
    else:
        for field_name, condition in prop.items():
            if isinstance(condition, dict) and "$has" in condition:
                factors.append({
                    "field": field_name,
                    "value": str(condition["$has"]),
                    "lift": round(lift, 2),
                })


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
    source: str
    confidence: float
    invoice_date: str | None = None
    due_days: int | None = None
    vat_pct: int | None = None
    gl_alternatives: list[dict] = field(default_factory=list)
    approver_alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "amount": self.amount,
            "invoice_date": self.invoice_date,
            "due_days": self.due_days,
            "vat_pct": self.vat_pct,
            "approver": self.approver,
            "approver_confidence": round(self.approver_confidence, 2),
            "gl_code": self.gl_code,
            "gl_label": self.gl_label,
            "gl_confidence": round(self.gl_confidence, 2),
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "gl_alternatives": self.gl_alternatives,
            "approver_alternatives": self.approver_alternatives,
        }


# ── Simple rules engine ────────────────────────────────────────────

RULES = [
    {
        "name": "Telia \u2192 Telecom",
        "match": lambda inv: inv["vendor"] == "Telia Finland",
        "gl_code": "6200",
        "approver": "Mikael H.",
    },
    {
        "name": "Elisa \u2192 Telecom",
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


def check_rules(invoice: dict) -> tuple[str, str, str] | None:
    """Check if any rule matches the invoice.

    Returns (gl_code, approver, rule_name) or None.
    """
    for rule in RULES:
        if rule["match"](invoice):
            return rule["gl_code"], rule["approver"], rule["name"]
    return None


def predict_invoice(client: AitoClient, invoice: dict) -> InvoicePrediction:
    """Predict GL code and approver for a single invoice."""
    invoice_id = invoice["invoice_id"]
    vendor = invoice["vendor"]
    amount = invoice["amount"]
    invoice_date = invoice.get("invoice_date")
    due_days = invoice.get("due_days")
    vat_pct = invoice.get("vat_pct")

    rule_match = check_rules(invoice)
    if rule_match:
        gl_code, approver, rule_name = rule_match
        rule_why = [{"field": "rule", "value": rule_name, "lift": 1.0}]
        gl_label = GL_LABELS.get(gl_code, gl_code)
        return InvoicePrediction(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            invoice_date=invoice_date,
            due_days=due_days,
            vat_pct=vat_pct,
            approver=f"AP / {approver}",
            approver_confidence=0.99,
            gl_code=gl_code,
            gl_label=gl_label,
            gl_confidence=0.99,
            source="rule",
            confidence=0.99,
            gl_alternatives=[{"value": gl_code, "display": f"{gl_code} \u2013 {gl_label}", "confidence": 0.99, "why": rule_why}],
            approver_alternatives=[{"value": approver, "display": f"AP / {approver}", "confidence": 0.99, "why": rule_why}],
        )

    where = {"vendor": vendor, "amount": amount}
    if "customer_id" in invoice:
        where["customer_id"] = invoice["customer_id"]
    if "category" in invoice:
        where["category"] = invoice["category"]

    try:
        gl_result = client.predict("invoices", where, "gl_code")
        approver_result = client.predict("invoices", where, "approver")
    except AitoError:
        return InvoicePrediction(
            invoice_id=invoice_id,
            vendor=vendor,
            amount=amount,
            invoice_date=invoice_date,
            due_days=due_days,
            vat_pct=vat_pct,
            approver=None,
            approver_confidence=0.0,
            gl_code=None,
            gl_label=None,
            gl_confidence=0.0,
            source="review",
            confidence=0.0,
        )

    gl_hits = gl_result.get("hits", [])
    approver_hits = approver_result.get("hits", [])

    gl_top = gl_hits[0] if gl_hits else None
    approver_top = approver_hits[0] if approver_hits else None

    gl_code = gl_top["feature"] if gl_top else None
    gl_conf = gl_top["$p"] if gl_top else 0.0
    approver_name = approver_top["feature"] if approver_top else None
    approver_conf = approver_top["$p"] if approver_top else 0.0

    overall_conf = min(gl_conf, approver_conf)
    source = "review" if overall_conf < REVIEW_THRESHOLD else "aito"

    return InvoicePrediction(
        invoice_id=invoice_id,
        vendor=vendor,
        amount=amount,
        invoice_date=invoice_date,
        due_days=due_days,
        vat_pct=vat_pct,
        approver=f"AP / {approver_name}" if approver_name else None,
        approver_confidence=approver_conf,
        gl_code=gl_code,
        gl_label=GL_LABELS.get(gl_code, gl_code) if gl_code else None,
        gl_confidence=gl_conf,
        source=source,
        confidence=overall_conf,
        gl_alternatives=_extract_alternatives(gl_hits, GL_LABELS),
        approver_alternatives=_extract_alternatives(approver_hits, prefix="AP / "),
    )


def predict_batch(client: AitoClient, invoices: list[dict], customer_id: str | None = None) -> list[InvoicePrediction]:
    """Predict GL code and approver for a batch of invoices."""
    if customer_id:
        invoices = [{**inv, "customer_id": customer_id} for inv in invoices]
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
    {"invoice_id": "INV-2852", "vendor": "W\u00e4rtsil\u00e4 Oyj", "amount": 28000.00, "category": "maintenance"},
]
