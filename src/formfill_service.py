"""Smart form fill service — multi-field prediction from vendor name.

Given a vendor name, predicts GL code, approver, cost centre, VAT %,
payment method, and due terms. Each prediction is an independent Aito
_predict call. In a production system these would run in parallel;
here they're sequential for simplicity and readability.
"""

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS

# Fields to predict, with display labels and formatting
PREDICT_FIELDS = [
    {"field": "gl_code", "label": "GL Account", "format": "gl"},
    {"field": "approver", "label": "Approver", "format": "text"},
    {"field": "cost_centre", "label": "Cost centre", "format": "text"},
    {"field": "vat_pct", "label": "VAT %", "format": "pct"},
    {"field": "payment_method", "label": "Payment method", "format": "text"},
    {"field": "due_days", "label": "Due terms", "format": "days"},
]

# Cost centre labels for display
COST_CENTRE_LABELS = {
    "CC-100": "General & Admin",
    "CC-210": "Retail Operations",
    "CC-300": "Facilities & Maintenance",
    "CC-400": "IT & Technology",
}


def format_value(value: str, fmt: str) -> str:
    """Format a predicted value for display."""
    if fmt == "gl":
        label = GL_LABELS.get(value, value)
        return f"{value} — {label}"
    if fmt == "pct":
        return f"{value}%"
    if fmt == "days":
        return f"Net {value} days"
    if fmt == "text":
        if value in COST_CENTRE_LABELS:
            return f"{value} — {COST_CENTRE_LABELS[value]}"
        return value
    return value


def predict_fields(client: AitoClient, vendor: str, amount: float | None = None) -> dict:
    """Predict all form fields for a given vendor.

    Returns a dict with field predictions and metadata:
    {
        "vendor": "Kesko Oyj",
        "fields": [
            {
                "field": "gl_code",
                "label": "GL Account",
                "value": "4400 — Supplies",
                "raw_value": "4400",
                "confidence": 0.91,
                "predicted": true
            },
            ...
        ],
        "predicted_count": 6,
        "avg_confidence": 0.89
    }
    """
    where = {"vendor": vendor}
    if amount is not None:
        where["amount"] = amount

    fields = []
    confidences = []

    for field_def in PREDICT_FIELDS:
        field_name = field_def["field"]
        try:
            result = client.predict("invoices", where, field_name)
            top = result["hits"][0] if result.get("hits") else None

            if top and top["$p"] > 0.10:
                raw_value = str(top["feature"])
                display_value = format_value(raw_value, field_def["format"])
                confidence = round(top["$p"], 2)
                fields.append({
                    "field": field_name,
                    "label": field_def["label"],
                    "value": display_value,
                    "raw_value": raw_value,
                    "confidence": confidence,
                    "predicted": True,
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
                })
        except AitoError:
            fields.append({
                "field": field_name,
                "label": field_def["label"],
                "value": None,
                "raw_value": None,
                "confidence": 0.0,
                "predicted": False,
            })

    predicted_count = sum(1 for f in fields if f["predicted"])
    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    return {
        "vendor": vendor,
        "fields": fields,
        "predicted_count": predicted_count,
        "avg_confidence": avg_confidence,
    }


# Known vendors for the dropdown — curated for demo variety
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
    "Wärtsilä Oyj",
]
