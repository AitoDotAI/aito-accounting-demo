"""Book tests for Aito _relate — pattern discovery for rule mining.

Examines how _relate finds statistical relationships between features,
producing human-readable rule candidates with exact support ratios.
"""

import json
import booktest as bt

from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_relate_category_to_gl_code(t: bt.TestCaseRun):
    """Find GL code patterns by category — the strongest signals."""
    c = get_client()

    t.h1("_relate: category → gl_code")
    t.tln("Each category should map to a single GL code with high support.")
    t.tln("These exact fractions (33/33) let accountants verify rules.")
    t.tln("")

    categories = ["telecom", "supplies", "food_bev", "office", "it_equipment", "facilities", "maintenance"]

    for cat in categories:
        result = c.relate("invoices", {"category": cat}, "gl_code")
        top = result["hits"][0]
        gl = top["related"]["gl_code"]["$has"]
        fs = top["fs"]
        f_on = int(fs["fOnCondition"])
        f_cond = int(fs["fCondition"])
        lift = top["lift"]
        ratio = f_on / f_cond if f_cond > 0 else 0
        strength = "STRONG" if ratio >= 0.95 else "review" if ratio >= 0.75 else "weak"
        t.iln(f"  {cat:20} → GL {gl}  {f_on}/{f_cond}  lift={lift:.1f}  [{strength}]")

    t.tln("")
    t.tln("Support ratios are exact historical counts from Aito statistics,")
    t.tln("not ML estimates. An accountant can verify each one.")


@bt.snapshot_httpx()
def test_relate_vendor_to_gl_code(t: bt.TestCaseRun):
    """Find GL code patterns by vendor — for vendor-specific rules."""
    c = get_client()

    t.h1("_relate: vendor → gl_code")
    t.tln("Vendor-specific patterns are narrower but very precise.")
    t.tln("")

    vendors = ["Kesko Oyj", "Telia Finland", "Fazer Bakeries", "SAP SE", "Kone Oyj"]

    for vendor in vendors:
        result = c.relate("invoices", {"vendor": vendor}, "gl_code")
        top = result["hits"][0]
        gl = top["related"]["gl_code"]["$has"]
        fs = top["fs"]
        f_on = int(fs["fOnCondition"])
        f_cond = int(fs["fCondition"])
        lift = top["lift"]
        t.iln(f"  {vendor:25} → GL {gl}  {f_on}/{f_cond}  lift={lift:.1f}")


@bt.snapshot_httpx()
def test_relate_override_patterns(t: bt.TestCaseRun):
    """Find patterns in human overrides — the feedback loop signal."""
    c = get_client()

    t.h1("_relate: override patterns")
    t.tln("Human overrides contain unformalized corrections. _relate")
    t.tln("surfaces which corrected values cluster together.")
    t.tln("")

    result = c.relate("overrides", {"field": "gl_code"}, "corrected_value")

    t.h2("GL code corrections")
    for hit in result["hits"]:
        corrected = hit["related"]["corrected_value"]["$has"]
        fs = hit["fs"]
        f_on = int(fs["fOnCondition"])
        lift = hit["lift"]
        if f_on >= 2:
            t.iln(f"  → {corrected:8}  count={f_on}  lift={lift:.2f}")

    t.tln("")
    t.tln("High-count corrections with consistent patterns become rule candidates.")
