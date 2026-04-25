"""Evaluation tests: measure prediction accuracy with _evaluate.

Uses testSource with limit to control evaluation size.
For full-scale evaluation, use jobs via the Aito Console.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_evaluate_gl_code(t: bt.TestCaseRun):
    """GL code accuracy for CUST-0000 (limited sample)."""
    c = get_client()

    t.h1("_evaluate: GL code accuracy (CUST-0000, 50 test samples)")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "testSource": {
            "from": "invoices",
            "where": {"customer_id": "CUST-0000"},
            "limit": 50,
        },
        "evaluate": {
            "from": "invoices",
            "where": {
                "customer_id": "CUST-0000",
                "vendor": {"$get": "vendor"},
                "category": {"$get": "category"},
            },
            "predict": "gl_code",
        },
    })

    t.iln(f"  Accuracy:      {result['accuracy']:.1%}")
    t.iln(f"  Base accuracy: {result['baseAccuracy']:.1%}")
    t.iln(f"  Accuracy gain: {result['accuracyGain']:.1%}")
    t.iln(f"  Test samples:  {result['testSamples']}")
    t.iln(f"  Geom mean p:   {result.get('geomMeanP', 0):.4f}")
    t.tln("")
    t.assertln("GL accuracy > 50%", result["accuracy"] > 0.50)


@bt.snapshot_httpx()
def test_evaluate_approver(t: bt.TestCaseRun):
    """Approver prediction accuracy (limited sample)."""
    c = get_client()

    t.h1("_evaluate: approver accuracy (CUST-0000, 50 test samples)")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "testSource": {
            "from": "invoices",
            "where": {"customer_id": "CUST-0000"},
            "limit": 50,
        },
        "evaluate": {
            "from": "invoices",
            "where": {
                "customer_id": "CUST-0000",
                "vendor": {"$get": "vendor"},
                "category": {"$get": "category"},
            },
            "predict": "approver",
        },
    })

    t.iln(f"  Accuracy:      {result['accuracy']:.1%}")
    t.iln(f"  Base accuracy: {result['baseAccuracy']:.1%}")
    t.iln(f"  Accuracy gain: {result['accuracyGain']:.1%}")
    t.iln(f"  Test samples:  {result['testSamples']}")
