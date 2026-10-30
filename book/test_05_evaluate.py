"""Evaluation tests: measure prediction accuracy with _evaluate.

Uses testSource with limit to control evaluation size.
For full-scale evaluation, use jobs via the Aito Console.
"""

import booktest as bt

from book.aito_env import get_client
from src.evaluation_service import run_evaluation


@bt.snapshot_httpx()
def test_evaluate_gl_code(t: bt.TestCaseRun):
    """GL code accuracy for CUST-0000 (limited sample)."""
    c = get_client()

    t.h1("_evaluate: GL code accuracy (CUST-0000, 50 test samples)")
    t.tln("")

    result = c.evaluate({
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

    result = c.evaluate({
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


@bt.snapshot_httpx()
def test_evaluate_approver_candidates_are_the_tenants_own(t: bt.TestCaseRun):
    """Whose staff the evaluations page may rank (td-20261030202058894219).

    `customer_id` in the evaluate `where` is evidence about the invoice.
    `approver` links to `employees`, so it does not bound the candidate
    employees -- only a filter on the linked row does. The remainder PR #58
    left behind: before the fix this query ranked all 1216 employees of 255
    tenants, the tenant's own employee won rank 1, and other tenants' staff
    took ranks 2 and on.
    """
    c = get_client()
    # One employee, so any other tenant's staff in the ranking is obvious.
    tenant = "CUST-0127"

    t.h1("Evaluations page: who may be ranked as CUST-0127's approver")
    t.tln("")

    result = run_evaluation(c, tenant, "invoices", "approver",
                            ["vendor", "amount", "category"], limit=50)
    where = result["meta"]["query"]["evaluate"]["where"]

    t.tln("The `where` the page sends, keys only:")
    for key in sorted(where):
        t.tln(f"  - {key}")
    t.tln("")

    shown = [case["predicted"] for case in result["cases"]]
    foreign_shown = [v for v in shown if not str(v).startswith(tenant + "-")]
    t.iln(f"  Cases on screen:                {len(shown)}")
    t.tln(f"  ...naming another tenant:       {len(foreign_shown)}")
    t.tln("")

    # The page prints one candidate per case (the top one). Resolve the
    # $get bindings against a real invoice and run the same `where` as a
    # predict to see the whole ranking that top came out of.
    row = c.search("invoices", {"customer_id": tenant}, limit=1)["hits"][0]
    probe = {k: (row.get(k) if isinstance(v, dict) and "$get" in v else v)
             for k, v in where.items()}
    ranked = [h["feature"]
              for h in c.predict("invoices", probe, "approver", limit=50)["hits"]]
    foreign = [(i + 1, v) for i, v in enumerate(ranked)
               if not str(v).startswith(tenant + "-")]

    t.iln(f"  Candidates ranked:              {len(ranked)}")
    t.tln(f"  ...belonging to another tenant: {len(foreign)}")
    if foreign:
        t.tln(f"  First foreign candidate:        rank {foreign[0][0]}, {foreign[0][1]}")
    t.tln("")
    t.assertln(not foreign, "a candidate belongs to another tenant")
