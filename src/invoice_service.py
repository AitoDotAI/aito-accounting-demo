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
    "4400": "Materials & Supplies",
    "4500": "Office Expenses",
    "4600": "Logistics",
    "5100": "Facilities",
    "5200": "Maintenance",
    "5300": "Insurance",
    "5400": "Professional Services",
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

    Linked-field factors (customer_id.name, customer_id.size_tier,
    customer_id.customer_id) are dropped: every query already filters
    on customer_id, so those propositions are restating the scope, not
    explaining the prediction.
    """
    if not why or not isinstance(why, dict):
        return []

    factors: list[dict] = []
    _walk_why(why, factors)
    factors = [f for f in factors if not f.get("field", "").startswith("customer_id.")]
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


# ── Rules engine ─────────────────────────────────────────────────
#
# Rules are mined per-customer from _relate patterns rather than hard-coded.
# A rule is {name, vendor, gl_code, approver} where historical support is
# >= 0.95 with at least 5 matching invoices. See mine_rules_for_customer()
# in quality_service.py.
#
# The legacy global RULES list is intentionally empty so any caller that
# still uses check_rules(invoice) without a rules argument gets "no rule
# applied" \u2014 which routes through Aito _predict, the safe fallback.
RULES: list[dict] = []


def check_rules(invoice: dict, rules: list[dict] | None = None) -> tuple[str, str, str] | None:
    """Check if any rule matches the invoice.

    Each rule is {name, vendor, gl_code, approver}. Match by vendor equality.
    Returns (gl_code, approver, rule_name) or None.

    If rules is None, falls back to the (empty) global RULES list.
    """
    rule_list = rules if rules is not None else RULES
    vendor = invoice.get("vendor")
    for rule in rule_list:
        if rule.get("vendor") and rule["vendor"] == vendor:
            return rule["gl_code"], rule["approver"], rule["name"]
    return None


def predict_invoice(client: AitoClient, invoice: dict, rules: list[dict] | None = None) -> InvoicePrediction:
    """Predict GL code and approver for a single invoice.

    If rules are provided (typically the per-customer set from
    mine_rules_for_customer), vendor-equality rules short-circuit the
    Aito call and produce source="rule".
    """
    from src.date_window import shift_iso

    invoice_id = invoice["invoice_id"]
    vendor = invoice["vendor"]
    amount = invoice["amount"]
    # invoice_date shifted to a rolling window so the demo never goes stale
    invoice_date = shift_iso(invoice.get("invoice_date"))
    due_days = invoice.get("due_days")
    vat_pct = invoice.get("vat_pct")

    rule_match = check_rules(invoice, rules=rules)
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
    # Description is a Text field in the schema; including it lets
    # Aito's analyzer match on tokens like "Monthly mobile
    # subscription" -> telecom GL, on top of the structured signals.
    if invoice.get("description"):
        where["description"] = invoice["description"]

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


def predict_batch(
    client: AitoClient,
    invoices: list[dict],
    customer_id: str | None = None,
    rules: list[dict] | None = None,
) -> list[InvoicePrediction]:
    """Predict GL code and approver for a batch of invoices.

    `rules` is the per-customer mined rules set; pass-through to
    predict_invoice so high-precision patterns short-circuit Aito calls.
    """
    if customer_id:
        invoices = [{**inv, "customer_id": customer_id} for inv in invoices]
    return [predict_invoice(client, inv, rules=rules) for inv in invoices]


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


