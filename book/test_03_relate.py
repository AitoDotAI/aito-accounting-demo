"""Rule mining tests: _relate for pattern discovery per customer.

Verifies that _relate finds vendor->GL patterns scoped by customer_id
and that support ratios are meaningful.
"""

import booktest as bt
from src.config import load_config
from src.aito_client import AitoClient


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_relate_vendor_to_gl(t: bt.TestCaseRun):
    """Find vendor -> GL code patterns for a specific customer."""
    c = get_client()

    t.h1("Rule mining: vendor -> GL code (CUST-0000)")
    t.tln("")

    # Get some vendors for this customer
    r = c.search("invoices", {"customer_id": "CUST-0000"}, limit=20)
    vendors = list({inv["vendor"] for inv in r["hits"]})[:5]

    for vendor in vendors:
        result = c.relate("invoices", {"customer_id": "CUST-0000", "vendor": vendor}, "gl_code")
        top = result["hits"][0]
        gl = top["related"]["gl_code"]["$has"]
        fs = top["fs"]
        f_on = int(fs["fOnCondition"])
        f_cond = int(fs["fCondition"])
        t.iln(f"  {vendor[:35]:35} -> GL {gl}  {f_on}/{f_cond}  lift={top['lift']:.1f}")

    t.tln("")
    t.tln("Support ratios are exact counts from this customer's data.")


@bt.snapshot_httpx()
def test_relate_patterns_conjunctions(t: bt.TestCaseRun):
    """Discover AND-conjunction rules with $patterns, for two targets.

    Mines from INPUTS only (vendor, category, vendor_country,
    amount_band) — never from outputs like approver — and shows both an
    output target: gl_code (incl. the capitalization rule) and approver
    (incl. the amount escalation). Sanity-checks each response: `related`
    is an $and of inputs, `condition` echoes the target, fOnCondition <= f.

    Note: $patterns' `fs` are smoothed model ESTIMATES (often fractional),
    used only to discover the conjunctions. The service recomputes exact
    support with _search counts before display — see rulemining_service.
    """
    c = get_client()
    inputs = ["vendor", "category", "vendor_country", "amount_band"]

    t.h1("Conjunction rule discovery: $patterns (CUST-0000)")
    t.tln("")

    # (target_field, target_value): a capitalization GL and the senior signer.
    for field, value in [("gl_code", "1600"), ("approver", "Markku Heikkinen")]:
        result = c.relate_patterns(
            "invoices",
            target={field: value},
            candidate_fields=inputs,
            where_filter={"customer_id": "CUST-0000"},
            k=8,
            limit=4,
        )
        t.tln(f"  {field} = {value}:")
        for hit in result["hits"]:
            # Customer scoping via nested `from` means the condition is
            # reliably the target field — the fs roles depend on it.
            assert field in hit["condition"], hit["condition"]
            fs = hit["fs"]
            f_on, f = int(fs["fOnCondition"]), int(fs["f"])
            assert f_on <= f, fs  # rows matching LHS AND target <= rows matching LHS
            if f_on < 3:
                continue  # too rare, or an anti-correlated candidate
            related = hit["related"]
            terms = related["$and"] if "$and" in related else [related]
            parts = []
            for term in terms:
                for fld, pred in term.items():
                    # Inputs only — assert no output leaked into a clause.
                    assert fld in inputs, f"non-input clause field: {fld}"
                    parts.append(f'{fld}="{pred["$has"]}"')
            precision = f_on / f if f else 0.0
            t.iln(f"    {' AND '.join(parts)}  (~{f_on}/{f} est, {precision:.0%})  lift={hit['lift']:.1f}")
        t.tln("")
    t.tln("Counts above are $patterns' smoothed estimates; the service uses")
    t.tln("exact _search counts for the displayed support.")


@bt.snapshot_httpx()
def test_relate_category_to_gl(t: bt.TestCaseRun):
    """Find category -> GL code patterns for a specific customer."""
    c = get_client()

    t.h1("Rule mining: category -> GL code (CUST-0000)")
    t.tln("")

    categories = ["telecom", "supplies", "facilities", "software", "consulting"]
    for cat in categories:
        result = c.relate("invoices", {"customer_id": "CUST-0000", "category": cat}, "gl_code")
        if result["hits"]:
            top = result["hits"][0]
            gl = top["related"]["gl_code"]["$has"]
            fs = top["fs"]
            f_on = int(fs["fOnCondition"])
            f_cond = int(fs["fCondition"])
            t.iln(f"  {cat:20} -> GL {gl}  {f_on}/{f_cond}")
        else:
            t.iln(f"  {cat:20} -> no data")
