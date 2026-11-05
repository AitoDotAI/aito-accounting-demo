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
    t.assertln(result["accuracy"] > 0.50, "GL accuracy > 50%")


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


@bt.snapshot_httpx()
def test_evaluate_approver_what_the_tenant_filter_costs(t: bt.TestCaseRun):
    """What scoping the candidates does to the numbers the pages publish.

    The filter changes a published accuracy, so its cost is measured
    rather than assumed. Measured read-only on `env.master`, unscoped ->
    scoped, at 200 test samples:

    | tenant    | accuracy      | base | meanRank      | geomMeanP     |
    |-----------|---------------|------|---------------|---------------|
    | CUST-0032 | 0.835 - 0.845 | 0.62 | 0.18 - 0.16   | 0.648 - 0.652 |
    | CUST-0000 | 0.895 - 0.895 | 0.43 | 0.55 - 0.23   | 0.646 - 0.667 |
    | CUST-0007 | 0.845 - 0.840 | 0.60 | 4.92 - 0.17   | 0.548 - 0.576 |

    Accuracy is flat within a point: scoping the candidates costs nothing.
    `meanRank` is what actually moves, and it improves -- for CUST-0007,
    when Aito was wrong the correct approver sat nearly five ranks down,
    because other tenants' staff were ranked in between; scoped, it sits
    just behind the top. `geomMeanP` rises slightly too, so the published
    numbers get better, not worse.

    At 50 samples (what this test runs, to stay quick) the same tenants
    look noisier and can point the other way -- CUST-0032 reads
    0.86 -> 0.82 and 0.681 -> 0.648, which is two cases in fifty. The
    assertions below are therefore loose on purpose; the 200-sample table
    above is the measurement, not the test output.
    """
    c = get_client()
    tenant = "CUST-0032"   # the one tenant whose accuracy moved down

    t.h1("Approver accuracy with and without the tenant filter (CUST-0032)")
    t.tln("")

    def evaluate(scoped: bool) -> dict:
        where = {"customer_id": tenant, "vendor": {"$get": "vendor"},
                 "amount": {"$get": "amount"}, "category": {"$get": "category"}}
        if scoped:
            where["approver.customer_id"] = tenant
        return c.evaluate({
            "testSource": {"from": "invoices", "where": {"customer_id": tenant},
                           "limit": 50},
            "evaluate": {"from": "invoices", "where": where, "predict": "approver"},
            "select": ["accuracy", "baseAccuracy", "meanRank", "geomMeanP",
                       "testSamples"],
        })

    # The unscoped query is what shipped before td-20261030202058894219;
    # it is run here only as the comparison.
    unscoped, scoped = evaluate(False), evaluate(True)

    for label, r in (("every tenant's staff", unscoped), ("this tenant's staff", scoped)):
        t.iln(f"  candidates: {label}")
        t.iln(f"    accuracy      {r['accuracy']:.1%}  (base {r['baseAccuracy']:.1%})")
        t.iln(f"    meanRank      {r.get('meanRank', 0):.2f}")
        t.iln(f"    geomMeanP     {r.get('geomMeanP', 0):.4f}")
        t.iln(f"    testSamples   {r['testSamples']}")
    t.tln("")

    # Both sides are one sample of fifty: the gate is "the filter does not
    # cost real accuracy", not an exact number.
    t.assertln(scoped["accuracy"] >= unscoped["accuracy"] - 0.10,
               f"scoping cost {unscoped['accuracy'] - scoped['accuracy']:.1%} of accuracy")
    t.assertln(scoped["meanRank"] <= unscoped["meanRank"] + 0.10,
               "scoping pushed the correct approver down the ranking")
