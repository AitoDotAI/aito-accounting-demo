"""/api/quality/evaluate refuses requests it should never send to Aito.

`limit` came straight from the query string, unbounded, while the page's
slider stops at 300 and says "capped at 300 to keep latency bounded" --
a cap only the browser enforced. `_evaluate` with a large limit over a
cross-tenant candidate set saturated the shared instance on 2026-10-31
(inFlightWeight 30 of 32), and the only guard in front of it is a
per-IP rate limit, so any visitor could do the same with a URL.

These are the request-level refusals; each must happen before any Aito
call, so the tests hand the service a client that records its calls.
"""

import pytest

from src.evaluation_service import MAX_LIMIT, run_evaluation, refuse_unusable_request

TENANT = "CUST-0127"


class RecordingClient:
    def __init__(self):
        self.bodies = []

    def evaluate(self, body, timeout=None):
        self.bodies.append(body)
        return {}


@pytest.mark.parametrize("limit", [MAX_LIMIT + 1, 5000, 0, -1])
def test_a_limit_outside_the_range_the_page_offers_is_refused_without_calling_aito(limit):
    client = RecordingClient()

    with pytest.raises(ValueError, match="limit"):
        run_evaluation(client, TENANT, "invoices", "gl_code", ["vendor"], limit=limit)

    assert client.bodies == []


def test_the_largest_limit_the_page_offers_is_accepted():
    refuse_unusable_request("invoices", "gl_code", MAX_LIMIT, ["vendor"])


@pytest.mark.parametrize("domain,predict", [
    ("nope", "gl_code"),
    ("invoices", "iban"),
    ("invoices", "approver.customer_id"),
])
def test_an_unknown_domain_or_target_is_refused_before_the_cache_or_aito(domain, predict):
    with pytest.raises(ValueError, match="Unknown"):
        refuse_unusable_request(domain, predict, 100, ["vendor"])


# ── input_fields: only the domain's own features, never the target ──────
#
# `input_fields` came straight from the query string. A target listed as
# its own input is a $get on the answer: predict=approver&input_fields=approver
# scores ~100% by reading the label. An unknown name is sent to Aito and
# comes back as a 200 carrying an error, and each spelling is a new cache key.

@pytest.mark.parametrize("domain,predict,fields", [
    ("invoices", "approver", ["approver"]),
    ("invoices", "approver", ["vendor", "approver"]),
    ("help", "article_id", ["page", "article_id"]),
])
def test_a_target_is_never_its_own_input(domain, predict, fields):
    with pytest.raises(ValueError, match="own input"):
        refuse_unusable_request(domain, predict, 100, fields)


@pytest.mark.parametrize("fields", [["iban"], ["vendor", "approver.customer_id"], ["customer_id"]])
def test_an_input_the_domain_does_not_offer_is_refused(fields):
    with pytest.raises(ValueError, match="Unknown input"):
        refuse_unusable_request("invoices", "gl_code", 100, fields)


def test_the_inputs_the_page_offers_are_accepted():
    refuse_unusable_request("invoices", "gl_code", 100, ["vendor", "amount", "category"])
    refuse_unusable_request("help", "clicked", 100, ["page", "article_id"])
