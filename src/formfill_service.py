"""Smart form fill service — multi-field prediction.

Given any combination of known fields, predicts the remaining fields.
Type a vendor → GL code, approver, VAT fill in. Type an amount →
predictions refine. Each field returns top-3 alternatives with $why
explanations so the UI can show dropdowns and factor breakdowns.
"""

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS, _extract_alternatives, _extract_why_factors

# Fields that can be predicted, with display labels and formatting
PREDICT_FIELDS = [
    {"field": "vendor", "label": "Vendor", "format": "text"},
    {"field": "gl_code", "label": "GL Account", "format": "gl"},
    {"field": "approver", "label": "Approver", "format": "text"},
    {"field": "cost_centre", "label": "Cost centre", "format": "text"},
    {"field": "vat_pct", "label": "VAT %", "format": "pct"},
    {"field": "payment_method", "label": "Payment method", "format": "text"},
    {"field": "due_days", "label": "Due terms", "format": "days"},
]

# All field names that can be used as input context
INPUT_FIELDS = {"vendor", "amount", "gl_code", "approver", "cost_centre",
                "vat_pct", "payment_method", "due_days", "category"}

COST_CENTRE_LABELS = {
    "CC-100": "General & Admin",
    "CC-210": "Retail Operations",
    "CC-300": "Facilities & Maintenance",
    "CC-400": "IT & Technology",
}


def _label_map_for_field(field_name: str) -> dict | None:
    if field_name == "gl_code":
        return GL_LABELS
    if field_name == "cost_centre":
        return COST_CENTRE_LABELS
    return None


def format_value(value: str, fmt: str) -> str:
    """Format a predicted value for display."""
    if fmt == "gl":
        label = GL_LABELS.get(value, value)
        return f"{value} \u2014 {label}"
    if fmt == "pct":
        return f"{value}%"
    if fmt == "days":
        return f"Net {value} days"
    if fmt == "text":
        if value in COST_CENTRE_LABELS:
            return f"{value} \u2014 {COST_CENTRE_LABELS[value]}"
        return value
    return value


def predict_fields(client: AitoClient, where: dict) -> dict:
    """Predict form fields not already provided in `where`.

    Accepts any combination of known fields as input context.
    Returns predictions for the remaining fields, each with top-3
    alternatives and $why explanations.
    """
    # Determine which fields to predict (skip fields already provided)
    provided = set(where.keys())
    fields_to_predict = [
        fd for fd in PREDICT_FIELDS
        if fd["field"] not in provided
    ]

    fields = []
    confidences = []

    for field_def in fields_to_predict:
        field_name = field_def["field"]
        try:
            result = client.predict("invoices", where, field_name)
            hits = result.get("hits", [])
            top = hits[0] if hits else None

            if top and top["$p"] > 0.10:
                raw_value = str(top["feature"])
                display_value = format_value(raw_value, field_def["format"])
                confidence = round(top["$p"], 4)

                label_map = _label_map_for_field(field_name)
                alternatives = _extract_alternatives(hits, label_map)

                fields.append({
                    "field": field_name,
                    "label": field_def["label"],
                    "value": display_value,
                    "raw_value": raw_value,
                    "confidence": round(confidence, 2),
                    "predicted": True,
                    "alternatives": alternatives,
                })
                confidences.append(confidence)
            else:
                fields.append({
                    "field": field_name,
                    "label": field_def["label"],
                    "value": None,
                    "raw_value": None,
                    "confidence": 0.0,
                    "predicted": False,
                    "alternatives": [],
                })
        except AitoError:
            fields.append({
                "field": field_name,
                "label": field_def["label"],
                "value": None,
                "raw_value": None,
                "confidence": 0.0,
                "predicted": False,
                "alternatives": [],
            })

    predicted_count = sum(1 for f in fields if f["predicted"])
    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    return {
        "where": where,
        "fields": fields,
        "predicted_count": predicted_count,
        "avg_confidence": avg_confidence,
    }


KNOWN_VENDORS = [
    "Kesko Oyj",
    "Telia Finland",
    "Fazer Bakeries",
    "SOK Corporation",
    "Verkkokauppa.com",
    "Kone Oyj",
    "ISS Palvelut",
    "SAP SE",
    "Microsoft Ireland",
    "Hartwall Oy",
    "Elisa Oyj",
    "W\u00e4rtsil\u00e4 Oyj",
]
