"""Anomaly detection service — inverse prediction pattern.

Uses Aito _predict in reverse: for each invoice, predict fields that
should be highly predictable (GL code, approver). Low $p means the
data doesn't fit known patterns — that's the anomaly signal.

No separate anomaly model needed. The same _predict engine used for
routing doubles as an anomaly detector.
"""

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.invoice_service import GL_LABELS


@dataclass
class AnomalyFlag:
    invoice_id: str
    vendor: str
    amount: float
    title: str
    description: str
    recommendation: str
    category: str  # "gl_mismatch", "amount_outlier", "unfamiliar", "approver"
    anomaly_score: float
    severity: str  # "high", "medium", "low"

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "amount": self.amount,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "category": self.category,
            "anomaly_score": round(self.anomaly_score, 2),
            "severity": self.severity,
        }


def classify_severity(score: float) -> str:
    """Classify anomaly score into severity levels."""
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def scan_invoice(client: AitoClient, invoice: dict) -> AnomalyFlag | None:
    """Scan a single invoice for anomalies using inverse prediction.

    Predicts GL code and approver from the invoice's features. If Aito
    is confident (high $p), the invoice fits known patterns. If not,
    something is unusual.

    Returns an AnomalyFlag if anomalous, None if normal.
    """
    vendor = invoice["vendor"]
    amount = invoice["amount"]
    invoice_id = invoice["invoice_id"]

    where = {"vendor": vendor, "amount": amount}
    if "customer_id" in invoice:
        where["customer_id"] = invoice["customer_id"]
    if "category" in invoice:
        where["category"] = invoice["category"]

    try:
        gl_result = client.predict("invoices", where, "gl_code")
        approver_result = client.predict("invoices", where, "approver")
    except AitoError:
        return None

    gl_top = gl_result["hits"][0] if gl_result.get("hits") else None
    approver_top = approver_result["hits"][0] if approver_result.get("hits") else None

    gl_p = gl_top["$p"] if gl_top else 0.0
    approver_p = approver_top["$p"] if approver_top else 0.0
    gl_predicted = gl_top["feature"] if gl_top else "?"
    approver_predicted = approver_top["feature"] if approver_top else "?"

    # Anomaly score: 1 - max confidence across predicted fields
    max_p = max(gl_p, approver_p)
    anomaly_score = 1.0 - max_p

    # GL mismatch is a separate signal: Aito is confident about
    # what the GL should be, but the stated GL is different
    stated_gl = invoice.get("gl_code")
    if stated_gl and stated_gl != gl_predicted and gl_p > 0.50:
        # Override anomaly score — the mismatch itself is the anomaly
        anomaly_score = max(anomaly_score, gl_p * 0.8)

    # Only flag if anomaly score is above threshold
    if anomaly_score < 0.15:
        return None

    # Build human-readable description
    title, desc, recommendation, category = _describe_anomaly(
        invoice, gl_predicted, gl_p, approver_predicted, approver_p,
    )

    return AnomalyFlag(
        invoice_id=invoice_id,
        vendor=vendor,
        amount=amount,
        title=title,
        description=desc,
        recommendation=recommendation,
        category=category,
        anomaly_score=anomaly_score,
        severity=classify_severity(anomaly_score),
    )


def _describe_anomaly(
    invoice: dict,
    gl_predicted: str,
    gl_p: float,
    approver_predicted: str,
    approver_p: float,
) -> tuple[str, str, str, str]:
    """Generate (title, description, recommendation, category) for an anomaly.

    Each anomaly category gets a concrete actionable next step rather than
    a generic numeric score.
    """
    vendor = invoice["vendor"]
    amount = invoice["amount"]
    stated_gl = invoice.get("gl_code")

    # Potential fraud signal: large round-number amount to a vendor Aito
    # has very weak history for. Round amounts (no cents, divisible by
    # 1000) above €10K with no clear approver pattern is a known
    # forensic-accounting red flag (manufactured invoices often use
    # round amounts; reviewers tend to wave them through).
    is_round = amount >= 10000 and amount % 1000 == 0
    if is_round and gl_p < 0.40 and approver_p < 0.40:
        return (
            f"Potential fraud signal — round €{amount:,.0f} to weak-history vendor {vendor}",
            f"€{amount:,.0f} is a round amount (no cents, divisible by 1000) to a vendor "
            f"with no strong historical routing pattern (GL {int(gl_p * 100)}%, approver "
            f"{int(approver_p * 100)}%). Manufactured invoices commonly use round amounts.",
            "Escalate to compliance / internal audit. Verify the PO, the vendor "
            "registration, and confirm the approver actually authorised this.",
            "fraud_signal",
        )

    # GL code mismatch — highest signal, suggests data-entry error or shifted policy
    if stated_gl and stated_gl != gl_predicted and gl_p > 0.50:
        pred_label = GL_LABELS.get(gl_predicted, gl_predicted)
        stated_label = GL_LABELS.get(stated_gl, stated_gl)
        return (
            f"GL code mismatch — uses {stated_gl} ({stated_label}), expected {gl_predicted} ({pred_label})",
            f"For {vendor}, {int(gl_p * 100)} of 100 historical invoices use GL {gl_predicted} ({pred_label}). "
            f"This invoice uses GL {stated_gl} ({stated_label}) instead.",
            f"Send back to processor — confirm whether GL {stated_gl} is intentional or a data-entry error.",
            "gl_mismatch",
        )

    # Both predictions weak — unfamiliar pattern (new vendor, unusual combination)
    if gl_p < 0.40 and approver_p < 0.40:
        return (
            f"Unfamiliar pattern — {vendor}",
            f"Aito has limited history for this vendor + amount + category combination. "
            f"GL prediction confidence {int(gl_p * 100)}%, approver {int(approver_p * 100)}%.",
            "Verify this is a known supplier; if first-time vendor, escalate to procurement for onboarding.",
            "unfamiliar",
        )

    # Low GL confidence — unusual GL for this vendor
    if gl_p < 0.50:
        pred_label = GL_LABELS.get(gl_predicted, gl_predicted)
        return (
            f"Unusual GL assignment — {vendor}",
            f"Aito's top GL prediction is {gl_predicted} ({pred_label}) but only at "
            f"{int(gl_p * 100)}% confidence — this vendor's GL pattern is inconsistent.",
            f"Confirm with vendor or processor; consider promoting a stable rule once pattern stabilizes.",
            "unfamiliar",
        )

    # Low approver confidence — routing anomaly
    if approver_p < 0.50:
        return (
            f"Unusual routing — {vendor}",
            f"Approver prediction is {approver_predicted} but only at {int(approver_p * 100)}% confidence. "
            f"This vendor's approval routing has changed or is irregular.",
            "Verify with the previous approver before processing.",
            "approver",
        )

    # Generic catch-all -- give the operator the actual numbers so they
    # can decide whether the threshold caught a real issue or noise.
    pred_label = GL_LABELS.get(gl_predicted, gl_predicted)
    return (
        f"Borderline confidence — {vendor}",
        (
            f"Aito's top GL prediction for this {vendor} invoice is "
            f"{gl_predicted} ({pred_label}) at {int(gl_p * 100)}%; approver "
            f"{approver_predicted} at {int(approver_p * 100)}%. Both "
            f"clear individual thresholds, but the combined confidence "
            f"sits in the review band -- the vendor + amount + category "
            f"combination doesn't perfectly match any prior pattern."
        ),
        "Review manually -- the prediction is plausible but doesn't have a single dominant signal. Confirm GL and approver, or override.",
        "unfamiliar",
    )


def scan_all(client: AitoClient, customer_id: str | None = None) -> dict:
    """Scan invoices for anomalies for a customer."""
    # Fetch a sample of invoices for this customer
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        result = client.search("invoices", where, limit=15)
        scan_invoices = result.get("hits", [])
    except AitoError:
        scan_invoices = []

    flags = []
    for invoice in scan_invoices:
        flag = scan_invoice(client, invoice)
        if flag is not None:
            flags.append(flag)

    # Sort by anomaly score (highest first)
    flags.sort(key=lambda f: f.anomaly_score, reverse=True)

    high = sum(1 for f in flags if f.severity == "high")
    medium = sum(1 for f in flags if f.severity == "medium")
    low = sum(1 for f in flags if f.severity == "low")

    return {
        "flags": [f.to_dict() for f in flags],
        "metrics": {
            "total": len(flags),
            "high": high,
            "medium": medium,
            "low": low,
            "scanned": len(scan_invoices),
        },
    }
