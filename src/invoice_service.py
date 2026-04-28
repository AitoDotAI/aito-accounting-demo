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
    factor may be a lift on a proposition like
    `{vendor: {$has: "Kesko"}}`. With `highlight` requested in the
    select, factors on Text fields also carry an `highlight` array
    of `{field, highlight: "matched <mark>tokens</mark>"}`.

    We preserve the per-factor *grouping* -- a single factor may
    correspond to a conjunction across multiple fields ($and) -- so
    the UI can render "When description is <mark>...</mark> and
    category is <mark>...</mark>" as one card with one lift.

    Returns a list of factor dicts:
        {type: "base", base_p: 0.46, target_value: "..."}        # base probability
        {type: "pattern", lift: 2.0, propositions: [             # one pattern card
            {field: "description", highlight: "Monthly <mark>...</mark>"},
            {field: "category", value: "telecom"},
        ]}

    Linked-field factors (customer_id.name, customer_id.size_tier,
    customer_id.customer_id) are dropped: every query already filters
    on customer_id, so those propositions are restating the scope, not
    explaining the prediction.
    """
    if not why or not isinstance(why, dict):
        return []

    out: list[dict] = []
    _walk_why_grouped(why, out)
    # Order: base first, then patterns by descending |lift - 1|. Top 5
    # so a noisy long tail of small lifts doesn't fill the popup.
    base = [f for f in out if f.get("type") == "base"]
    patterns = [f for f in out if f.get("type") == "pattern"]
    patterns.sort(key=lambda f: abs(f.get("lift", 1) - 1), reverse=True)
    return base + patterns[:5]


def _walk_why_grouped(node: dict, out: list[dict]) -> None:
    """Walk the $why tree and emit one entry per top-level factor.

    Aito $why shape (verified against the live API with
    select: [..., {"$why": {"highlight": {"posPreTag": ..., "posPostTag": ...}}}]):

      relatedPropositionLift = {
        type: "relatedPropositionLift",
        value: <lift>,
        proposition: {<field>: {$has: <value>}}                     # single
                  or {$and: [{<f1>: {$has: ...}}, {<f2>: {$has: ...}}, ...]}
        highlight: [
          {field: "$context.<fieldname>",                           # NOT "invoices.<x>"
           highlight: "<full original text with <mark> around matched tokens>",
           score: <float>},
          ...
        ]
      }

    The `highlight` array is per-field (not per-proposition), and
    each entry's `highlight` string is the FULL value of that field
    in the request, with the matched tokens wrapped in mark tags.
    Multiple `$has` propositions on the same field collapse into
    ONE highlight entry with all matched tokens marked inside the
    same context string.

    We emit:
      {type: "base", base_p: float, target_value: str}
      {type: "pattern", lift: float,
        highlights: [{field, html}, ...]   # when Aito returned highlights
        propositions: [{field, value}, ...]} # always, as a fallback for fields without highlights

    customer_id and customer_id.* propositions/highlights are dropped:
    every query already filters on customer_id, so those factors are
    just restating the scope.
    """
    t = node.get("type")
    if t == "baseP":
        prop = node.get("proposition", {})
        base_p = float(node.get("value", 0) or 0)
        target_value = None
        for _f, cond in prop.items():
            if isinstance(cond, dict) and "$has" in cond:
                target_value = str(cond["$has"])
                break
        out.append({"type": "base", "base_p": round(base_p, 4), "target_value": target_value})
    elif t == "relatedPropositionLift":
        lift = float(node.get("value", 0) or 0)
        # Drop noise: lifts close to 1.0 contribute nothing.
        if abs(lift - 1.0) < 0.05:
            return

        # 1. Flatten propositions (handles $and).
        propositions: list[dict] = []
        _collect_props(node.get("proposition", {}), propositions)
        # Drop customer_id-scope propositions.
        propositions = [
            p for p in propositions
            if p["field"] != "customer_id"
            and not p["field"].startswith("customer_id.")
        ]
        if not propositions:
            return  # Entire factor was customer_id scope -- nothing left to show.

        # 2. Highlights, keyed by field. Strip the "$context." prefix
        # and skip customer_id-scoped highlights.
        highlights: list[dict] = []
        for h in node.get("highlight") or []:
            field = h.get("field", "")
            if field.startswith("$context."):
                field = field[len("$context."):]
            if field == "customer_id" or field.startswith("customer_id."):
                continue
            html = h.get("highlight", "")
            if not html:
                continue
            highlights.append({"field": field, "html": html})

        out.append({
            "type": "pattern",
            "lift": round(lift, 2),
            "propositions": propositions,
            "highlights": highlights,
        })
    # Don't recurse into product/related children -- the top-level
    # tree usually has one product node containing the relevant
    # baseP + relatedPropositionLift children.
    for child in node.get("factors", []):
        if isinstance(child, dict):
            _walk_why_grouped(child, out)


def _collect_props(prop: dict, out: list[dict]) -> None:
    if "$and" in prop:
        for sub in prop["$and"]:
            _collect_props(sub, out)
        return
    for field_name, cond in prop.items():
        if not isinstance(cond, dict):
            continue
        # $has = exact value match (categorical fields)
        if "$has" in cond:
            out.append({"field": field_name, "value": str(cond["$has"])})
        # $match = text token match (Text fields)
        elif "$match" in cond:
            out.append({"field": field_name, "value": str(cond["$match"])})


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
    vendor_country: str | None = None
    category: str | None = None
    description: str | None = None
    gl_alternatives: list[dict] = field(default_factory=list)
    approver_alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "vendor_country": self.vendor_country,
            "category": self.category,
            "description": self.description,
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
    vendor_country = invoice.get("vendor_country")
    category = invoice.get("category")
    description = invoice.get("description")

    rule_match = check_rules(invoice, rules=rules)
    if rule_match:
        gl_code, approver, rule_name = rule_match
        # Mined-rule explanations look like a single pattern card with
        # one proposition (the rule name) and lift 1.0 — same grouped
        # shape as Aito _predict $why factors so the renderer is uniform.
        rule_why = [{
            "type": "pattern",
            "lift": 1.0,
            "propositions": [{"field": "rule", "value": rule_name}],
        }]
        gl_label = GL_LABELS.get(gl_code, gl_code)
        return InvoicePrediction(
            invoice_id=invoice_id,
            vendor=vendor,
            vendor_country=vendor_country,
            category=category,
            description=description,
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
            vendor_country=vendor_country,
            category=category,
            description=description,
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
        vendor_country=vendor_country,
        category=category,
        description=description,
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


