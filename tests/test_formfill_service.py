"""Tests for the smart form fill service.

Tests verify multi-field prediction, value formatting, and graceful
handling of unknown vendors and Aito errors.
"""

import pytest
import httpx

from src.aito_client import AitoClient
from src.config import Config
from src.formfill_service import format_value, predict_fields, PREDICT_FIELDS

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)


def _mock_predict_response(feature, p=0.90):
    return {"offset": 0, "total": 1, "hits": [
        {"$p": p, "feature": feature, "$why": {"type": "product"}},
    ]}


class TestFormatValue:
    def test_gl_code_includes_label(self):
        assert format_value("4400", "gl") == "4400 — Supplies"

    def test_unknown_gl_code_uses_raw_value(self):
        assert format_value("9999", "gl") == "9999 — 9999"

    def test_pct_appends_percent_sign(self):
        assert format_value("24", "pct") == "24%"

    def test_days_formats_as_net_terms(self):
        assert format_value("30", "days") == "Net 30 days"

    def test_cost_centre_includes_label(self):
        assert format_value("CC-210", "text") == "CC-210 — Retail Operations"

    def test_plain_text_passes_through(self):
        assert format_value("Sanna L.", "text") == "Sanna L."


class TestPredictFields:
    def test_all_six_fields_predicted_for_known_vendor(self, httpx_mock):
        """A well-known vendor should get all 6 fields predicted."""
        # Mock responses for each predict call (6 fields)
        httpx_mock.add_response(json=_mock_predict_response("4400", 0.91))  # gl_code
        httpx_mock.add_response(json=_mock_predict_response("Sanna L.", 0.88))  # approver
        httpx_mock.add_response(json=_mock_predict_response("CC-210", 0.85))  # cost_centre
        httpx_mock.add_response(json=_mock_predict_response("24", 0.99))  # vat_pct
        httpx_mock.add_response(json=_mock_predict_response("SEPA Credit Transfer", 0.97))  # payment_method
        httpx_mock.add_response(json=_mock_predict_response("30", 0.92))  # due_days

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, "Kesko Oyj")

        assert result["vendor"] == "Kesko Oyj"
        assert result["predicted_count"] == 6
        assert result["avg_confidence"] > 0.80
        assert len(result["fields"]) == 6

        # Check specific fields
        gl = next(f for f in result["fields"] if f["field"] == "gl_code")
        assert gl["raw_value"] == "4400"
        assert gl["value"] == "4400 — Supplies"
        assert gl["confidence"] == 0.91
        assert gl["predicted"] is True

        vat = next(f for f in result["fields"] if f["field"] == "vat_pct")
        assert vat["value"] == "24%"

    def test_low_confidence_fields_not_predicted(self, httpx_mock):
        """Fields with confidence below 0.10 should not be marked as predicted."""
        httpx_mock.add_response(json=_mock_predict_response("4400", 0.05))  # too low
        httpx_mock.add_response(json=_mock_predict_response("Sanna L.", 0.03))
        httpx_mock.add_response(json=_mock_predict_response("CC-210", 0.02))
        httpx_mock.add_response(json=_mock_predict_response("24", 0.01))
        httpx_mock.add_response(json=_mock_predict_response("SEPA", 0.04))
        httpx_mock.add_response(json=_mock_predict_response("30", 0.06))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, "Completely Unknown Corp")

        assert result["predicted_count"] == 0
        assert result["avg_confidence"] == 0.0

    def test_aito_error_produces_unpredicted_fields(self, httpx_mock):
        """If Aito fails, all fields should be unpredicted (not crash)."""
        for _ in range(6):
            httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, "Kesko Oyj")

        assert result["predicted_count"] == 0
        assert len(result["fields"]) == 6
        assert all(not f["predicted"] for f in result["fields"])

    def test_amount_included_in_where_clause(self, httpx_mock):
        """When amount is provided, it should be in the Aito query."""
        for _ in range(6):
            httpx_mock.add_response(json=_mock_predict_response("4400", 0.90))

        client = AitoClient(TEST_CONFIG)
        predict_fields(client, "Kesko Oyj", amount=4220.0)

        import json
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["where"]["amount"] == 4220.0

    def test_result_structure_matches_expected_shape(self, httpx_mock):
        """Verify the full response structure for API consumers."""
        for _ in range(6):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.80))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, "Test Vendor")

        assert "vendor" in result
        assert "fields" in result
        assert "predicted_count" in result
        assert "avg_confidence" in result

        for field in result["fields"]:
            assert "field" in field
            assert "label" in field
            assert "value" in field
            assert "raw_value" in field
            assert "confidence" in field
            assert "predicted" in field
