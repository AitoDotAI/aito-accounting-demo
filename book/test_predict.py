"""Book tests for Aito _predict — the core prediction operator.

Examines how _predict behaves for GL code and approver predictions
across different vendors, showing confidence levels and $why factors.
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_predict_gl_code_known_vendor(t: bt.TestCaseRun):
    """Predict GL code for a well-known vendor (Kesko Oyj)."""
    c = get_client()

    t.h1("GL code prediction: Kesko Oyj")
    t.tln("Kesko is a Finnish retail conglomerate. With 18 invoices in the")
    t.tln("dataset, Aito should predict GL 4400 (Supplies) with high confidence.")
    t.tln("")

    result = c.predict("invoices", {"vendor": "Kesko Oyj", "amount": 4220}, "gl_code")

    t.h2("Top predictions")
    for hit in result["hits"][:5]:
        t.iln(f"  GL {hit['feature']:6}  p={hit['$p']:.4f}")

    t.tln("")
    t.h2("$why explanation for top prediction")
    why = result["hits"][0].get("$why", {})
    t.icode(json.dumps(why, indent=2)[:800], "json")

    t.tln("")
    top = result["hits"][0]
    t.assertln(f"Top prediction is 4400", top["feature"] == "4400")
    t.assertln(f"Confidence > 0.80", top["$p"] > 0.80)


@bt.snapshot_httpx()
def test_predict_gl_code_unknown_vendor(t: bt.TestCaseRun):
    """Predict GL code for an unknown vendor — Aito should be uncertain."""
    c = get_client()

    t.h1("GL code prediction: Unknown vendor")
    t.tln("When Aito hasn't seen a vendor before, confidence should be low.")
    t.tln("This is the honest uncertainty that makes the demo compelling.")
    t.tln("")

    result = c.predict("invoices", {"vendor": "Brand New Corp", "amount": 45000}, "gl_code")

    t.h2("Top predictions")
    for hit in result["hits"][:5]:
        t.iln(f"  GL {hit['feature']:6}  p={hit['$p']:.4f}")

    t.tln("")
    top = result["hits"][0]
    t.assertln(f"Confidence < 0.50 (uncertain)", top["$p"] < 0.50)


@bt.snapshot_httpx()
def test_predict_approver_by_vendor(t: bt.TestCaseRun):
    """Compare approver predictions across different vendors."""
    c = get_client()

    t.h1("Approver prediction by vendor")
    t.tln("Different vendors route to different approvers based on")
    t.tln("historical patterns in the dataset.")
    t.tln("")

    vendors = [
        ("Kesko Oyj", "Sanna L."),
        ("Telia Finland", "Mikael H."),
        ("Kone Oyj", "Tiina M."),
        ("ISS Palvelut", "Tiina M."),
        ("Verkkokauppa.com", "Mikael H."),
    ]

    for vendor, expected in vendors:
        result = c.predict("invoices", {"vendor": vendor}, "approver")
        top = result["hits"][0]
        correct = top["feature"] == expected
        mark = "ok" if correct else "WRONG"
        t.iln(f"  {vendor:25} → {top['feature']:12} p={top['$p']:.3f}  expected={expected}  [{mark}]")

    t.tln("")
    t.tln("Approver routing is driven by vendor → department → approver patterns.")


@bt.snapshot_httpx()
def test_predict_with_category_context(t: bt.TestCaseRun):
    """Show how adding category as context improves prediction confidence."""
    c = get_client()

    t.h1("Effect of category context on GL prediction")
    t.tln("Adding the category field to the where clause should improve")
    t.tln("confidence because it's a strong signal for GL code.")
    t.tln("")

    vendor = "Kesko Oyj"

    # Without category
    r1 = c.predict("invoices", {"vendor": vendor}, "gl_code")
    p1 = r1["hits"][0]["$p"]

    # With category
    r2 = c.predict("invoices", {"vendor": vendor, "category": "supplies"}, "gl_code")
    p2 = r2["hits"][0]["$p"]

    t.iln(f"  Without category: GL {r1['hits'][0]['feature']}  p={p1:.4f}")
    t.iln(f"  With category:    GL {r2['hits'][0]['feature']}  p={p2:.4f}")
    t.iln(f"  Improvement:      {(p2-p1):.4f}")

    t.tln("")
    t.assertln("Category improves confidence", p2 >= p1)
