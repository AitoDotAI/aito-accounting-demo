"""Booktest coverage for the endpoints added in P1 / P2:
formfill submit logging, mined rules, and rule
drill-down. Each captures a snapshot of live Aito behavior so future
regressions in these flows are caught.
"""

import time
import uuid

import booktest as bt

from book.aito_env import get_client

from src.quality_service import mine_rules_for_customer


@bt.snapshot_httpx()
def test_mine_rules_for_customer(t: bt.TestCaseRun):
    """Mined per-customer rules: vendor → GL with support and lift."""
    c = get_client()

    t.h1("Mined rules (CUST-0000)")
    t.tln("")
    t.tln("Rules where support_ratio >= 0.95 and at least 5 matches.")
    t.tln("")

    rules = mine_rules_for_customer(c, "CUST-0000", top_n=8)
    t.iln(f"  {len(rules)} rules mined")
    t.tln("")
    for r in rules[:8]:
        t.iln(f"  {r['vendor'][:30]:30} -> GL {r['gl_code']:5}  "
              f"support {r['support_match']}/{r['support_total']} "
              f"({r['support_ratio']*100:.0f}%)  lift {r['lift']}x  "
              f"approver {r['approver']}")

    t.tln("")
    t.assertln(len(rules) >= 1, "at least 1 rule mined")
    if rules:
        t.assertln(rules[0]["support_ratio"] >= 0.95, "first rule has support_ratio >= 0.95")


@bt.snapshot_httpx()
def test_prediction_log_schema_exists(t: bt.TestCaseRun):
    """The prediction_log table is created with the expected columns."""
    c = get_client()

    t.h1("prediction_log schema")
    t.tln("")

    schema = c.get_schema()["schema"]
    if "prediction_log" not in schema:
        t.iln("prediction_log table not yet created — run ./do reset-data")
        t.assertln(False, "prediction_log table missing - run ./do reset-data")
        return

    cols = sorted(schema["prediction_log"]["columns"].keys())
    for col in cols:
        col_def = schema["prediction_log"]["columns"][col]
        t.iln(f"  {col:20} type={col_def['type']:10} nullable={col_def.get('nullable', False)}")

    t.tln("")
    expected = {"log_id", "customer_id", "field", "predicted_value",
                "user_value", "source", "confidence", "accepted", "timestamp"}
    t.assertln(expected.issubset(set(cols)), "all expected columns present")
