"""The evaluation surfaces rank only the tenant's own staff (td-20261030202058894219).

The remainder PR #58 (td-20260901082623647538) left behind. Form Fill was
fixed; the two evaluation surfaces still predict `approver` with
`customer_id` as evidence only. `approver` links to `employees`, so that
bounds which invoices Aito learns from, not which employees it may rank
— measured read-only on shared 2.11.9 against `env.master`, the where
`run_evaluation` builds offers another tenant's staff from rank 2:

| tenant    | staff | own at rank 1 | 1st foreign rank | foreign in top 10 |
|-----------|-------|---------------|------------------|-------------------|
| CUST-0127 | 1     | yes           | 2                | 9                 |
| CUST-0007 | 20    | yes           | 2                | 9                 |
| CUST-0100 | 2     | yes           | 3                | 8                 |
| CUST-0000 | 160   | yes           | 4                | 3                 |

`_evaluate` returns only the top candidate per case, and in the ten
tenants probed the tenant's own employee won every rank 1 — so no foreign
name has been seen on screen. What ships today is a ranking over all 1216
employees of 255 tenants, one rank away from
`frontend/app/quality/predictions/page.tsx:367`, which prints
`cases[].predicted` verbatim. The accuracy and meanRank the quality pages
publish are measured against that same inflated candidate set.
"""

import pytest

from src.evaluation_service import run_evaluation
from src.quality_service import compute_evaluations_matrix

TENANT = "CUST-0127"


class RecordingClient:
    """Answers every _evaluate with one case and records each request body."""

    def __init__(self):
        self.bodies: list[dict] = []

    def evaluate(self, body, timeout=None):
        self.bodies.append(body)
        predict = body["evaluate"]["predict"]
        return {
            "accuracy": 1.0, "baseAccuracy": 1.0, "accuracyGain": 0.0,
            "meanRank": 1.0, "geomMeanP": 0.9, "testSamples": 1, "trainSamples": 125,
            "cases": [{
                "testCase": {"invoice_id": "INV-1", predict: f"{TENANT}-EMP-0000"},
                "accurate": True,
                "top": {"feature": f"{TENANT}-EMP-0000", "$p": 0.99, "field": predict},
            }],
        }

    # compute_evaluations_matrix only evaluates; the rest of the page's
    # queries are exercised by tests/test_quality_service.py.
    def search(self, table, where, limit=10):
        return {"hits": []}

    def relate(self, table, where, relate_field):
        return {"hits": []}

    def where_for(self, predict: str) -> dict:
        """The evaluate `where` recorded for one predict target."""
        return next(b["evaluate"]["where"] for b in self.bodies
                    if b["evaluate"]["predict"] == predict)


def test_the_evaluations_page_limits_the_approver_to_the_customers_own_staff():
    client = RecordingClient()
    run_evaluation(client, TENANT, "invoices", "approver",
                   ["vendor", "amount", "category"], limit=50)
    assert client.where_for("approver")["approver.customer_id"] == TENANT


def test_no_other_predict_target_gets_the_employee_filter():
    client = RecordingClient()
    run_evaluation(client, TENANT, "invoices", "gl_code",
                   ["vendor", "amount", "category"], limit=50)
    assert "approver.customer_id" not in client.where_for("gl_code")


def test_the_quality_matrix_scopes_its_approver_task_too():
    # The matrix ships only aggregates, so it leaks no name — but it
    # publishes accuracy for a candidate set the product never uses.
    client = RecordingClient()
    compute_evaluations_matrix(client, TENANT)
    assert client.where_for("approver")["approver.customer_id"] == TENANT
    assert "approver.customer_id" not in client.where_for("gl_code")


def test_an_approver_is_never_evaluated_without_a_customer():
    # Without a tenant there is nothing to scope the candidates to, and
    # every tenant's staff would compete — the Form Fill rule (PR #58),
    # applied to the surface that measures it.
    with pytest.raises(ValueError, match="needs a customer_id"):
        run_evaluation(RecordingClient(), "", "invoices", "approver",
                       ["vendor", "amount", "category"], limit=50)


def test_an_unknown_predict_target_is_refused_rather_than_sent_to_aito():
    # `predict` arrives as a query parameter (src/app.py:1058). Scoping is
    # declared per target, so a target nobody declared cannot be scoped —
    # and must not reach Aito unscoped.
    client = RecordingClient()
    result = run_evaluation(client, TENANT, "invoices", "iban",
                            ["vendor", "amount", "category"], limit=50)
    assert "error" in result
    assert client.bodies == []


# ── The other two linked targets ────────────────────────────────────
#
# `approver` was the one the P1 named, so it was the one that got the
# filter. It is not the only target whose values live in a linked,
# tenant-scoped table: the matching domain predicts `invoice_id`
# (bank_transactions.invoice_id -> invoices.invoice_id) and the help
# domain predicts `article_id` (help_impressions.article_id ->
# help_articles.article_id). Both linked tables carry customer_id, so
# both candidate sets span all 255 tenants without a filter.
#
# This is worse than the approver case on one axis and better on
# another. Worse: `cases[].predicted` prints the predicted id verbatim,
# and an invoice_id or article_id belonging to another tenant is a
# recognisable foreign identifier, not a name that happens to lose.
# Better: the quality matrix predicts `vendor_name` and `clicked` for
# these domains, not the ids, so only the evaluation surface is exposed.


def test_the_linked_invoice_target_ranks_only_the_customers_own_invoices():
    client = RecordingClient()
    run_evaluation(client, TENANT, "matching", "invoice_id",
                   ["description", "amount"], limit=50)
    assert client.where_for("invoice_id")["invoice_id.customer_id"] == TENANT


def test_the_article_target_is_not_scoped_to_the_tenant_because_that_drops_global_articles():
    # help_articles.customer_id is "*" for every app and legal article, so an
    # exact `article_id.customer_id == tenant` puts the true answer of every
    # global-article impression outside the candidates. The product's own
    # set is {"$or": ["*", tenant]}, which `_evaluate` cannot take (literal
    # where values only). Until it can, this target is left as it was.
    client = RecordingClient()
    run_evaluation(client, TENANT, "help", "article_id", ["page"], limit=50)
    assert "article_id.customer_id" not in client.where_for("article_id")


def test_the_unlinked_targets_in_those_domains_keep_no_filter():
    # vendor_name is a plain column on bank_transactions and `clicked` is
    # a boolean: neither has a linked table to bound, and a filter there
    # would narrow the training evidence for no reason.
    client = RecordingClient()
    run_evaluation(client, TENANT, "matching", "vendor_name",
                   ["description", "amount"], limit=50)
    run_evaluation(client, TENANT, "help", "clicked", ["page"], limit=50)
    assert "invoice_id.customer_id" not in client.where_for("vendor_name")
    assert "article_id.customer_id" not in client.where_for("clicked")


@pytest.mark.parametrize("domain,predict,inputs", [
    ("matching", "invoice_id", ["description", "amount"]),
])
def test_a_scoped_linked_target_is_never_evaluated_without_a_customer(domain, predict, inputs):
    with pytest.raises(ValueError, match="needs a customer_id"):
        run_evaluation(RecordingClient(), "", domain, predict, inputs, limit=50)


# `bank_transactions.invoice_id` is nullable (src/data_loader.py:118), and
# `testSource` still includes unmatched payments. Measured on a local
# Aito 2.12.0 with a 15-tenant slice (docs/verification/evaluation-approver-
# scope.md): `trainSamples` is the same with and without the filter, so the
# filter does not remove those rows from training; accuracy is 0% both ways
# (each invoice has one bank line, so a held-out line's invoice has no
# training evidence) and `meanRank` is what moves (e.g. 7418 -> 33 for
# CUST-0127). That is a shown number changing, which the report flags.
