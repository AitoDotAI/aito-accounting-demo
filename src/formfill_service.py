"""Smart form fill service — multi-field prediction.

Given any combination of known fields, predicts the remaining fields.
Type a vendor → GL code, approver, VAT fill in. Type an amount →
predictions refine. Each field returns top-3 alternatives with $why
explanations so the UI can show dropdowns and factor breakdowns.
"""

from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient, AitoError, aito_call_log
from src.invoice_service import GL_LABELS, _extract_alternatives, _extract_why_factors

# Fields that can be predicted, with display labels and formatting.
#
# auto_prefill_threshold is the minimum confidence at which a prediction is
# returned as `predicted: True` (the field auto-fills in State 2 styling).
# Below the threshold the prediction is still returned as a suggestion in
# `alternatives` but the field stays empty — user must explicitly choose.
#
# High-cost fields (vendor, gl_code, approver) need high confidence because
# a wrong silent prefill goes to wrong account / wrong person.
# Low-cost fields (cost_centre, vat_pct, payment_method, due_days) prefill
# more aggressively because errors are trivially fixable.
PREDICT_FIELDS = [
    {"field": "vendor",         "label": "Vendor",         "format": "text", "auto_prefill_threshold": 0.95},
    {"field": "gl_code",        "label": "GL Account",     "format": "gl",   "auto_prefill_threshold": 0.85},
    {"field": "approver",       "label": "Approver",       "format": "text", "auto_prefill_threshold": 0.85},
    {"field": "cost_centre",    "label": "Cost centre",    "format": "text", "auto_prefill_threshold": 0.70},
    {"field": "vat_pct",        "label": "VAT %",          "format": "pct",  "auto_prefill_threshold": 0.60},
    {"field": "payment_method", "label": "Payment method", "format": "text", "auto_prefill_threshold": 0.70},
    {"field": "due_days",       "label": "Due terms",      "format": "days", "auto_prefill_threshold": 0.70},
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


def predict_template(client: AitoClient, customer_id: str, vendor: str) -> dict | None:
    """Find the most common historical invoice 'template' for this vendor.

    A template is the joint mode of (gl_code, approver, cost_centre, vat_pct,
    payment_method, due_days, category). When confidence is high, the user
    can apply all fields with one click instead of confirming each.

    `_search` here is the right primitive — not a Counter reinvention of
    `_predict`. We need the joint frequency P(gl ∧ approver ∧ cc | vendor)
    so the UI can claim "X of Y prior invoices use this exact routing".
    `_predict` returns calibrated marginal probabilities per field and
    has no single-call joint-mode form; expressing the same thing as
    chained _predicts would mean 7 round-trips per vendor, multiplied
    by the top-N when this is called from formfill_templates.
    """
    try:
        result = client.search("invoices", {"customer_id": customer_id, "vendor": vendor}, limit=50)
    except AitoError:
        return None

    hits = result.get("hits", [])
    if len(hits) < 3:
        return None

    from collections import Counter

    # Use the high-signal classification fields as the template key.
    # Other fields (vat, payment, due, category) have lower variation
    # so we resolve them as the most-common value within the matched set.
    def core_key(inv: dict) -> tuple:
        return (inv.get("gl_code"), inv.get("approver"), inv.get("cost_centre"))

    counts = Counter(core_key(inv) for inv in hits)
    if not counts:
        return None

    (gl, approver, cc), n = counts.most_common(1)[0]
    confidence = n / len(hits)

    if confidence < 0.20:  # too noisy to call it a template
        return None

    # Resolve secondary fields by most-common value within the matched template
    matched = [inv for inv in hits if core_key(inv) == (gl, approver, cc)]
    def mode_of(field: str):
        c = Counter(inv.get(field) for inv in matched if inv.get(field) is not None)
        return c.most_common(1)[0][0] if c else None

    return {
        "vendor": vendor,
        "match_count": n,
        "total_history": len(hits),
        "confidence": round(confidence, 2),
        "fields": {
            "gl_code": gl,
            "gl_label": GL_LABELS.get(gl, gl) if gl else None,
            "approver": approver,
            "cost_centre": cc,
            "vat_pct": mode_of("vat_pct"),
            "payment_method": mode_of("payment_method"),
            "due_days": mode_of("due_days"),
            "category": mode_of("category"),
        },
    }


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

    # Each predicted field is an independent _predict call against the
    # same (customer, vendor, …) context. Running them in series means
    # the user waits N × round-trip; the calls are pure and the Aito
    # client is httpx (sync, releases the GIL on I/O), so a small
    # ThreadPoolExecutor turns this into max(round-trip) instead of
    # sum(round-trip). For 5–7 fields at ~200ms each, the saved
    # latency is roughly 1s on a warm instance.
    #
    # Each worker thread inherits the parent's contextvars, so the
    # per-request `aito_call_log` accumulator captures every call's
    # latency for the X-Aito-Ms response header.
    log = aito_call_log.get()

    def predict_one(field_def: dict) -> dict:
        field_name = field_def["field"]
        threshold = field_def.get("auto_prefill_threshold", 0.85)
        empty = {
            "field": field_name,
            "label": field_def["label"],
            "value": None,
            "raw_value": None,
            "confidence": 0.0,
            "predicted": False,
            "auto_prefill_threshold": threshold,
            "below_threshold": False,
            "alternatives": [],
        }
        try:
            # Worker threads don't see the parent's ContextVar values,
            # so re-attach the log explicitly before the Aito call.
            if log is not None:
                aito_call_log.set(log)
            result = client.predict("invoices", where, field_name)
        except AitoError:
            return empty

        hits = result.get("hits", [])
        top = hits[0] if hits else None
        if not top or top["$p"] <= 0.10:
            return empty

        raw_value = str(top["feature"])
        display_value = format_value(raw_value, field_def["format"])
        confidence = round(top["$p"], 4)
        label_map = _label_map_for_field(field_name)
        alternatives = _extract_alternatives(hits, label_map)
        auto_prefill = confidence >= threshold
        return {
            "field": field_name,
            "label": field_def["label"],
            "value": display_value if auto_prefill else None,
            "raw_value": raw_value if auto_prefill else None,
            "confidence": round(confidence, 2),
            "predicted": auto_prefill,
            "auto_prefill_threshold": threshold,
            "below_threshold": not auto_prefill,
            "alternatives": alternatives,
        }

    if not fields_to_predict:
        fields = []
    else:
        # Cap workers so we don't open more sockets than needed.
        # 7 fields max, 7 threads is fine.
        with ThreadPoolExecutor(max_workers=min(8, len(fields_to_predict))) as pool:
            fields = list(pool.map(predict_one, fields_to_predict))

    # Original semantics: avg over all fields whose top hit passed the
    # 0.10 noise floor (predicted or not). predicted_count tracks only
    # those that crossed the per-field auto-prefill threshold.
    confidences = [f["confidence"] for f in fields if f["confidence"] > 0]
    predicted_count = sum(1 for f in fields if f["predicted"])
    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    return {
        "where": where,
        "fields": fields,
        "predicted_count": predicted_count,
        "avg_confidence": avg_confidence,
    }


