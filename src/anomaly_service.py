"""Anomaly detection service — inverse prediction pattern.

Uses Aito _predict in reverse: for each invoice, predict fields that
should be highly predictable (GL code, approver). Low $p means the
data doesn't fit known patterns — that's the anomaly signal.

No separate anomaly model needed. The same _predict engine used for
routing doubles as an anomaly detector.
"""

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError


@dataclass
class AnomalyFlag:
    invoice_id: str
    vendor: str
    amount: float
    title: str
    description: str
    anomaly_score: float
    severity: str  # "high", "medium", "low"

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "amount": self.amount,
            "title": self.title,
            "description": self.description,
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
    title, desc = _describe_anomaly(
        invoice, gl_predicted, gl_p, approver_predicted, approver_p,
    )

    return AnomalyFlag(
        invoice_id=invoice_id,
        vendor=vendor,
        amount=amount,
        title=title,
        description=desc,
        anomaly_score=anomaly_score,
        severity=classify_severity(anomaly_score),
    )


def _describe_anomaly(
    invoice: dict,
    gl_predicted: str,
    gl_p: float,
    approver_predicted: str,
    approver_p: float,
) -> tuple[str, str]:
    """Generate a human-readable title and description for an anomaly."""
    vendor = invoice["vendor"]
    amount = invoice["amount"]
    stated_gl = invoice.get("gl_code")
    anomaly_score = 1.0 - max(gl_p, approver_p)

    # GL code mismatch
    if stated_gl and stated_gl != gl_predicted and gl_p > 0.50:
        return (
            f"GL code mismatch — predicted {gl_predicted} but stated as {stated_gl}",
            f"{vendor} · Aito predicts GL {gl_predicted} with {gl_p:.0%} confidence, "
            f"but invoice uses {stated_gl} · score {anomaly_score:.2f}",
        )

    # Low confidence on everything — unknown pattern
    if gl_p < 0.40 and approver_p < 0.40:
        return (
            f"Unfamiliar pattern — {vendor}",
            f"Low prediction confidence for all fields · "
            f"GL {gl_predicted} ({gl_p:.0%}), approver {approver_predicted} ({approver_p:.0%}) "
            f"· score {anomaly_score:.2f}",
        )

    # Low GL confidence specifically
    if gl_p < 0.50:
        return (
            f"Unusual GL assignment — {vendor}",
            f"GL code prediction confidence only {gl_p:.0%} for {vendor} "
            f"€{amount:,.2f} · score {anomaly_score:.2f}",
        )

    # Low approver confidence
    if approver_p < 0.50:
        return (
            f"Unusual routing — {vendor}",
            f"Approver prediction confidence only {approver_p:.0%} for {vendor} "
            f"€{amount:,.2f} · score {anomaly_score:.2f}",
        )

    # Generic
    return (
        f"Anomalous invoice — {vendor}",
        f"Combined prediction confidence below threshold · score {anomaly_score:.2f}",
    )


# Demo invoices to scan — mix of normal and anomalous
DEMO_SCAN_INVOICES = [
    # Normal invoices (should not flag)
    {"invoice_id": "INV-2901", "vendor": "Telia Finland", "amount": 890.50, "category": "telecom"},
    {"invoice_id": "INV-2902", "vendor": "Kesko Oyj", "amount": 4220.00, "category": "supplies"},
    # Anomalous: unknown vendor + high amount
    {"invoice_id": "INV-2903", "vendor": "Brand New Corp", "amount": 45000.00},
    # Anomalous: wrong GL code for vendor
    {"invoice_id": "INV-2904", "vendor": "Kesko Oyj", "amount": 4220.00, "category": "supplies", "gl_code": "5100"},
    # Anomalous: huge amount for this vendor
    {"invoice_id": "INV-2905", "vendor": "Fazer Bakeries", "amount": 22400.00, "category": "food_bev"},
    # Normal
    {"invoice_id": "INV-2906", "vendor": "SOK Corporation", "amount": 7850.00, "category": "supplies"},
    # Anomalous: unknown vendor, moderate amount
    {"invoice_id": "INV-2907", "vendor": "Suspicious GmbH", "amount": 8750.00},
    # Normal
    {"invoice_id": "INV-2908", "vendor": "Elisa Oyj", "amount": 445.00, "category": "telecom"},
    # Anomalous: GL mismatch
    {"invoice_id": "INV-2909", "vendor": "Telia Finland", "amount": 1200.00, "category": "telecom", "gl_code": "4400"},
    # Normal
    {"invoice_id": "INV-2910", "vendor": "Verkkokauppa.com", "amount": 1299.00, "category": "it_equipment"},
]


def scan_all(client: AitoClient, customer_id: str | None = None) -> dict:
    """Scan invoices for anomalies for a customer."""
    # Fetch a sample of invoices for this customer
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        result = client.search("invoices", where, limit=30)
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
            "scanned": len(DEMO_SCAN_INVOICES),
        },
    }
