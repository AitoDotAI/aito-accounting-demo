"""Tests for the invoice prediction service.

Tests cover the hybrid rules + Aito architecture: rule matching,
Aito prediction fallback, review threshold, and metrics computation.
"""

import pytest

from src.aito_client import AitoClient, AitoError
from src.config import Config
from src.invoice_service import (
    REVIEW_THRESHOLD,
    _extract_alternatives,
    tenant_employee_names,
    check_rules,
    compute_metrics,
    predict_invoice,
    InvoicePrediction,
)

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)

# ── Rule matching ────────────��──────────────────────────────────────


class TestCheckRules:
    """Rules are now passed in per-call (mined per-customer), not global."""

    SAMPLE_RULES = [
        {"name": "Telia → Telecom", "vendor": "Telia Finland", "gl_code": "6200", "approver": "Mikael H."},
        {"name": "Elisa → Telecom", "vendor": "Elisa Oyj", "gl_code": "6200", "approver": "Mikael H."},
    ]

    def test_vendor_match_returns_rule(self):
        result = check_rules({"vendor": "Telia Finland", "amount": 890}, rules=self.SAMPLE_RULES)
        assert result[:2] == ("6200", "Mikael H.")

    def test_second_rule_matches(self):
        result = check_rules({"vendor": "Elisa Oyj", "amount": 500}, rules=self.SAMPLE_RULES)
        assert result[:2] == ("6200", "Mikael H.")

    def test_unknown_vendor_returns_none(self):
        result = check_rules({"vendor": "Unknown GmbH", "amount": 3000}, rules=self.SAMPLE_RULES)
        assert result is None

    def test_no_rules_provided_returns_none(self):
        """Default global RULES is empty — nothing matches."""
        result = check_rules({"vendor": "Telia Finland", "amount": 890})
        assert result is None


# ── Invoice prediction ──────────────────────────────────────────────


class TestPredictInvoice:
    def test_rule_match_returns_high_confidence_rule_source(self, httpx_mock):
        """When a per-customer rule matches the vendor, no Aito call is made."""
        client = AitoClient(TEST_CONFIG)
        rules = [
            {"name": "Telia → Telecom", "vendor": "Telia Finland", "gl_code": "6200", "approver": "Mikael H."},
        ]

        result = predict_invoice(client, {
            "invoice_id": "INV-001",
            "vendor": "Telia Finland",
            "amount": 890.50,
            "category": "telecom",
        }, rules=rules)

        assert result.source == "rule"
        assert result.gl_code == "6200"
        assert result.approver == "AP / Mikael H."
        assert result.confidence == 0.99

    def test_aito_prediction_above_threshold(self, httpx_mock):
        """Kesko should get an Aito prediction with high confidence."""
        # Mock GL code prediction
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": 0.91, "feature": "4400", "$why": {"type": "product"}},
            ]},
        )
        # Mock approver prediction
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": 0.88, "feature": "Sanna L.", "$why": {"type": "product"}},
            ]},
        )

        client = AitoClient(TEST_CONFIG)
        result = predict_invoice(client, {
            "invoice_id": "INV-002",
            "vendor": "Kesko Oyj",
            "amount": 4220.00,
            "category": "supplies",
        })

        assert result.source == "aito"
        assert result.gl_code == "4400"
        assert result.gl_label == "Materials & Supplies"
        assert result.approver == "AP / Sanna L."
        assert result.confidence == 0.88  # min(0.91, 0.88)

    def test_low_confidence_flags_for_review(self, httpx_mock):
        """Unknown vendor with low confidence should go to review."""
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": 0.25, "feature": "4400", "$why": {"type": "product"}},
            ]},
        )
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": 0.20, "feature": "Sanna L.", "$why": {"type": "product"}},
            ]},
        )

        client = AitoClient(TEST_CONFIG)
        result = predict_invoice(client, {
            "invoice_id": "INV-003",
            "vendor": "Unknown Vendor GmbH",
            "amount": 3100.00,
        })

        assert result.source == "review"
        assert result.confidence < REVIEW_THRESHOLD

    def test_aito_error_flags_for_review(self, httpx_mock):
        """If Aito is unreachable, invoice goes to review."""
        import httpx as httpx_lib

        # Client retries once on connection error before giving up
        for _ in range(2):
            httpx_mock.add_exception(
                httpx_lib.ConnectError("Connection refused"),
                url="https://test.aito.app/db/demo/api/v1/_predict",
            )

        client = AitoClient(TEST_CONFIG)
        result = predict_invoice(client, {
            "invoice_id": "INV-004",
            "vendor": "Kesko Oyj",
            "amount": 4220.00,
        })

        assert result.source == "review"
        assert result.confidence == 0.0


# ── Metrics ───────────���─────────────────────────────────────────────


class TestComputeMetrics:
    def test_mixed_sources_computes_correct_rates(self):
        predictions = [
            InvoicePrediction("INV-1", "A", 100, "AP/X", 0.99, "4400", "Supplies", 0.99, "rule", 0.99),
            InvoicePrediction("INV-2", "B", 200, "AP/Y", 0.88, "4100", "COGS", 0.91, "aito", 0.88),
            InvoicePrediction("INV-3", "C", 300, "AP/Z", 0.85, "6200", "Telecom", 0.92, "aito", 0.85),
            InvoicePrediction("INV-4", "D", 400, None, 0.0, None, None, 0.0, "review", 0.0),
        ]

        metrics = compute_metrics(predictions)

        assert metrics["total"] == 4
        assert metrics["rule_count"] == 1
        assert metrics["aito_count"] == 2
        assert metrics["review_count"] == 1
        assert metrics["automation_rate"] == 0.75  # 3/4
        assert metrics["avg_confidence"] == 0.91  # avg of 0.99, 0.88, 0.85

    def test_empty_predictions_returns_zeros(self):
        metrics = compute_metrics([])

        assert metrics["automation_rate"] == 0
        assert metrics["avg_confidence"] == 0

    def test_to_dict_includes_all_fields(self):
        pred = InvoicePrediction(
            "INV-1", "Kesko", 4220, "AP / Sanna L.", 0.88,
            "4400", "Supplies", 0.91, "aito", 0.88,
        )
        d = pred.to_dict()

        assert d["invoice_id"] == "INV-1"
        assert d["vendor"] == "Kesko"
        assert d["amount"] == 4220
        assert d["gl_code"] == "4400"
        assert d["gl_label"] == "Supplies"
        assert d["source"] == "aito"


class TestApproverIsResolvedToAName:
    """`approver` stores an employee_id and links to `employees`.

    It used to store a NAME, which could not link and — because 42% of
    employee names are shared between tenants — pooled every same-named
    approver's history into one value. The candidate set is now confined
    server-side by `approver.customer_id`, and the id the model returns
    is resolved to a person for display.
    """

    def test_the_predicted_id_is_shown_as_a_person_not_a_key(self):
        hits = [{"feature": "CUST-0000-EMP-0156", "$p": 0.91}]
        names = {"CUST-0000-EMP-0156": "Matti Niemi"}

        alts = _extract_alternatives(hits, names, prefix="AP / ",
                                     label_replaces_value=True)

        assert alts[0]["display"] == "AP / Matti Niemi"
        # The id stays the machine-readable value: it is what an override
        # is recorded against, and it is unique where a name is not.
        assert alts[0]["value"] == "CUST-0000-EMP-0156"

    def test_a_gl_code_still_shows_its_code_alongside_the_label(self):
        # The two label maps are not interchangeable: an accountant works
        # with the GL code itself, so it is shown as well as its meaning.
        alts = _extract_alternatives([{"feature": "4400", "$p": 0.9}],
                                     {"4400": "Office supplies"})

        assert alts[0]["display"] == "4400 \u2013 Office supplies"

    def test_an_unresolvable_id_falls_back_to_the_id(self):
        # An employee who has left is absent from the roster but still
        # appears in history. Showing the raw id is ugly; showing nothing
        # would drop a real alternative.
        alts = _extract_alternatives([{"feature": "CUST-0000-EMP-9999", "$p": 0.5}],
                                     {"CUST-0000-EMP-0156": "Matti Niemi"},
                                     prefix="AP / ", label_replaces_value=True)

        assert alts[0]["display"] == "AP / CUST-0000-EMP-9999"

    def test_names_are_not_fetched_without_a_tenant(self):
        # A prediction with no customer_id is not tenant-scoped, so there
        # is no roster to resolve against and no round trip worth making.
        class ExplodingClient:
            def search(self, *a, **k):
                raise AssertionError("should not query without a customer_id")

        assert tenant_employee_names(ExplodingClient(), "") == {}
