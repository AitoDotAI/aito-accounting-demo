"""Book tests for anomaly detection — inverse prediction pattern.

Shows how low $p on predictable fields signals anomalies without
a separate anomaly model.
"""

import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_anomaly_normal_vs_unusual(t: bt.TestCaseRun):
    """Compare prediction confidence for normal vs anomalous invoices."""
    c = get_client()

    t.h1("Anomaly detection: normal vs unusual invoices")
    t.tln("Same _predict engine, used in reverse. High confidence = normal.")
    t.tln("Low confidence = data doesn't fit known patterns = anomaly.")
    t.tln("")

    test_cases = [
        ("Normal: Kesko Oyj, supplies", {"vendor": "Kesko Oyj", "amount": 4220, "category": "supplies"}),
        ("Normal: Telia Finland, telecom", {"vendor": "Telia Finland", "amount": 890, "category": "telecom"}),
        ("Anomaly: unknown vendor", {"vendor": "Brand New Corp", "amount": 45000}),
        ("Anomaly: Kesko wrong GL context", {"vendor": "Kesko Oyj", "amount": 4220, "gl_code": "5100"}),
    ]

    t.h2("GL code prediction confidence")
    for label, where in test_cases:
        result = c.predict("invoices", where, "gl_code")
        top = result["hits"][0]
        anomaly_score = 1 - top["$p"]
        flag = "ANOMALY" if anomaly_score > 0.30 else "normal"
        t.iln(f"  {label:45} gl={top['feature']}  p={top['$p']:.3f}  anomaly={anomaly_score:.3f}  [{flag}]")

    t.tln("")
    t.tln("No separate anomaly model. No threshold tuning. Just _predict.")
