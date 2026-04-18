"""Tests for the smart form fill service.

Tests verify multi-field prediction from any input combination,
value formatting, alternatives with $why, and graceful error handling.
"""

import pytest
import httpx

from src.aito_client import AitoClient
from src.config import Config
from src.formfill_service import format_value, predict_fields

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)


def _mock_predict_response(feature, p=0.90):
    return {"offset": 0, "total": 1, "hits": [
        {"$p": p, "feature": feature, "$why": {"type": "product", "factors": []}},
    ]}


class TestFormatValue:
    def test_gl_code_includes_label(self):
        assert "4400" in format_value("4400", "gl")
        assert "Supplies" in format_value("4400", "gl")

    def test_pct_appends_percent_sign(self):
        assert format_value("24", "pct") == "24%"

    def test_days_formats_as_net_terms(self):
        assert format_value("30", "days") == "Net 30 days"

    def test_cost_centre_includes_label(self):
        result = format_value("CC-210", "text")
        assert "CC-210" in result
        assert "Retail Operations" in result

    def test_plain_text_passes_through(self):
        assert format_value("Sanna L.", "text") == "Sanna L."


class TestPredictFields:
    def test_predicts_remaining_fields_given_vendor(self, httpx_mock):
        """Given vendor, should predict 6 remaining fields (not vendor)."""
        for _ in range(6):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.90))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"vendor": "Kesko Oyj"})

        # vendor is provided, so 6 other fields should be predicted
        assert result["predicted_count"] == 6
        field_names = [f["field"] for f in result["fields"]]
        assert "vendor" not in field_names  # vendor was provided, not predicted
        assert "gl_code" in field_names

    def test_predicts_remaining_fields_given_amount(self, httpx_mock):
        """Given only amount, should predict all 7 fields including vendor."""
        for _ in range(7):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.80))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"amount": 4220})

        field_names = [f["field"] for f in result["fields"]]
        assert "vendor" in field_names  # vendor not provided, so predicted
        assert result["predicted_count"] == 7

    def test_skips_provided_fields(self, httpx_mock):
        """Fields in the where clause should not be predicted."""
        for _ in range(5):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.90))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"vendor": "Kesko Oyj", "gl_code": "4400"})

        field_names = [f["field"] for f in result["fields"]]
        assert "vendor" not in field_names
        assert "gl_code" not in field_names
        assert result["predicted_count"] == 5

    def test_returns_alternatives_with_why(self, httpx_mock):
        """Each field should include alternatives array."""
        httpx_mock.add_response(json={
            "offset": 0, "total": 2, "hits": [
                {"$p": 0.91, "feature": "4400", "$why": {"type": "product", "factors": [
                    {"type": "relatedPropositionLift", "proposition": {"vendor": {"$has": "Kesko"}}, "value": 6.4},
                ]}},
                {"$p": 0.04, "feature": "6100", "$why": {"type": "product", "factors": []}},
            ],
        })
        # Mock remaining 5 fields
        for _ in range(5):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.80))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"vendor": "Kesko Oyj"})

        gl = next(f for f in result["fields"] if f["field"] == "gl_code")
        assert "alternatives" in gl
        assert len(gl["alternatives"]) == 2
        assert gl["alternatives"][0]["confidence"] == 0.91

    def test_low_confidence_fields_not_predicted(self, httpx_mock):
        """Fields below 0.10 confidence should not be marked predicted."""
        for _ in range(6):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.05))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"vendor": "Unknown Corp"})

        assert result["predicted_count"] == 0

    def test_aito_error_produces_unpredicted_fields(self, httpx_mock):
        """If Aito fails, all fields should be unpredicted."""
        for _ in range(6):
            httpx_mock.add_exception(httpx.ConnectError("refused"))

        client = AitoClient(TEST_CONFIG)
        result = predict_fields(client, {"vendor": "Kesko Oyj"})

        assert result["predicted_count"] == 0
        assert all(not f["predicted"] for f in result["fields"])

    def test_where_clause_passed_to_aito(self, httpx_mock):
        """The where dict should be forwarded to Aito queries."""
        for _ in range(6):
            httpx_mock.add_response(json=_mock_predict_response("test", 0.90))

        client = AitoClient(TEST_CONFIG)
        predict_fields(client, {"vendor": "Kesko Oyj", "amount": 4220})

        import json
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["where"]["vendor"] == "Kesko Oyj"
        assert body["where"]["amount"] == 4220
