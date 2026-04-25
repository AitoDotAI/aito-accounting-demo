"""Book tests evaluating payment matching accuracy with _evaluate.

Uses Aito's _evaluate to measure whether invoice_id can be predicted
from bank transaction features. This answers: is there a learnable
pattern, or is this a problem without a solution?
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_evaluate_invoice_id_from_description_and_amount(t: bt.TestCaseRun):
    """Can Aito predict the specific invoice_id from description + amount?"""
    c = get_client()

    t.h1("_evaluate: invoice_id from description + amount")
    t.tln("Can Aito learn which specific invoice a bank transaction belongs to?")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "test": {"$index": {"$mod": [4, 0]}},
        "evaluate": {
            "from": "bank_transactions",
            "where": {
                "description": {"$get": "description"},
                "amount": {"$get": "amount"},
            },
            "predict": "invoice_id",
        },
    })

    t.h2("Results")
    t.iln(f"  Accuracy:      {result['accuracy']:.1%}")
    t.iln(f"  Base accuracy: {result['baseAccuracy']:.1%}")
    t.iln(f"  Mean rank:     {result['meanRank']:.1f} / {result['trainSamples'] + result['testSamples']:.0f}")
    t.iln(f"  Test samples:  {result['testSamples']}")
    t.iln(f"  Geom mean p:   {result['geomMeanP']:.4f}")
    t.tln("")
    t.tln("Accuracy 0% means Aito cannot predict the specific invoice_id")
    t.tln("from description + amount alone. Each invoice_id is unique —")
    t.tln("there is no repeating pattern to learn from.")


@bt.snapshot_httpx()
def test_evaluate_vendor_name_from_description(t: bt.TestCaseRun):
    """Can Aito predict vendor_name from description? (Should be much better.)"""
    c = get_client()

    t.h1("_evaluate: vendor_name from description")
    t.tln("Vendor resolution should be much easier — there are only 17")
    t.tln("vendors and the description text contains vendor name tokens.")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "test": {"$index": {"$mod": [4, 0]}},
        "evaluate": {
            "from": "bank_transactions",
            "where": {
                "description": {"$get": "description"},
            },
            "predict": "vendor_name",
        },
    })

    t.h2("Results")
    t.iln(f"  Accuracy:      {result['accuracy']:.1%}")
    t.iln(f"  Base accuracy: {result['baseAccuracy']:.1%}")
    t.iln(f"  Accuracy gain: {result['accuracyGain']:.1%}")
    t.iln(f"  Mean rank:     {result['meanRank']:.1f} / 17 vendors")
    t.iln(f"  Test samples:  {result['testSamples']}")
    t.iln(f"  Geom mean p:   {result['geomMeanP']:.4f}")
    t.tln("")
    t.tln("Vendor resolution works well because description tokens")
    t.tln("(kesko, telia, sok) directly identify the vendor.")


@bt.snapshot_httpx()
def test_evaluate_gl_code_from_vendor_and_amount(t: bt.TestCaseRun):
    """GL code prediction accuracy for comparison."""
    c = get_client()

    t.h1("_evaluate: gl_code from vendor + amount (reference)")
    t.tln("")

    result = c._request("POST", "/_evaluate", json={
        "test": {"$index": {"$mod": [4, 0]}},
        "evaluate": {
            "from": "invoices",
            "where": {
                "vendor": {"$get": "vendor"},
                "amount": {"$get": "amount"},
                "category": {"$get": "category"},
            },
            "predict": "gl_code",
        },
    })

    t.h2("Results")
    t.iln(f"  Accuracy:      {result['accuracy']:.1%}")
    t.iln(f"  Base accuracy: {result['baseAccuracy']:.1%}")
    t.iln(f"  Accuracy gain: {result['accuracyGain']:.1%}")
    t.iln(f"  Test samples:  {result['testSamples']}")
    t.iln(f"  Geom mean p:   {result['geomMeanP']:.4f}")
    t.tln("")
    t.tln("GL code prediction is a well-structured problem: 7 possible")
    t.tln("values, strong vendor→GL patterns. This is where Aito shines.")
