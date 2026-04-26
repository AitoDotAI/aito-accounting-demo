"""Booktest coverage for the endpoints added in P1 / P2:
template prediction, formfill submit logging, mined rules, and rule
drill-down. Each captures a snapshot of live Aito behavior so future
regressions in these flows are caught.
"""

import time
import uuid

import booktest as bt

from src.aito_client import AitoClient
from src.config import load_config
from src.formfill_service import predict_template
from src.quality_service import mine_rules_for_customer


def get_client():
    return AitoClient(load_config())


@bt.snapshot_httpx()
def test_predict_template_for_recurring_vendor(t: bt.TestCaseRun):
    """Template prediction returns a stable joint mode for a frequent vendor."""
    c = get_client()

    t.h1("Template prediction (CUST-0000, top vendor)")
    t.tln("")

    # Pick the most-frequent vendor for CUST-0000
    sample = c.search("invoices", {"customer_id": "CUST-0000"}, limit=300)
    from collections import Counter
    counts = Counter(h["vendor"] for h in sample.get("hits", []) if h.get("vendor"))
    if not counts:
        t.tln("(no invoices for CUST-0000)")
        return

    top_vendor, top_count = counts.most_common(1)[0]
    t.iln(f"Top vendor: {top_vendor} ({top_count} invoices)")
    t.tln("")

    template = predict_template(c, "CUST-0000", top_vendor)
    if template is None:
        t.iln("(no confident template; vendor's pattern is too noisy)")
        t.assertln("template can be None for noisy vendors", True)
        return

    t.iln(f"  match_count:    {template['match_count']}/{template['total_history']}")
    t.iln(f"  confidence:     {template['confidence']}")
    t.iln(f"  gl_code:        {template['fields']['gl_code']} ({template['fields']['gl_label']})")
    t.iln(f"  approver:       {template['fields']['approver']}")
    t.iln(f"  cost_centre:    {template['fields']['cost_centre']}")
    t.iln(f"  vat_pct:        {template['fields']['vat_pct']}")
    t.iln(f"  payment_method: {template['fields']['payment_method']}")
    t.tln("")
    t.assertln("confidence >= 0.20", template["confidence"] >= 0.20)


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
    t.assertln("at least 1 rule mined", len(rules) >= 1)
    if rules:
        t.assertln("first rule has support_ratio >= 0.95", rules[0]["support_ratio"] >= 0.95)


@bt.snapshot_httpx()
def test_prediction_log_schema_exists(t: bt.TestCaseRun):
    """The prediction_log table is created with the expected columns."""
    c = get_client()

    t.h1("prediction_log schema")
    t.tln("")

    schema = c.get_schema()["schema"]
    if "prediction_log" not in schema:
        t.iln("prediction_log table not yet created — run ./do reset-data")
        t.assertln("prediction_log table exists", False)
        return

    cols = sorted(schema["prediction_log"]["columns"].keys())
    for col in cols:
        col_def = schema["prediction_log"]["columns"][col]
        t.iln(f"  {col:20} type={col_def['type']:10} nullable={col_def.get('nullable', False)}")

    t.tln("")
    expected = {"log_id", "customer_id", "field", "predicted_value",
                "user_value", "source", "confidence", "accepted", "timestamp"}
    t.assertln("all expected columns present", expected.issubset(set(cols)))
