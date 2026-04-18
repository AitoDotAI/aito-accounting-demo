"""Tests for the quality dashboard service.

Tests verify automation breakdown computation and override statistics.
"""

import pytest

from src.aito_client import AitoClient
from src.config import Config
from src.quality_service import compute_automation_breakdown, compute_override_stats

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)


class TestComputeAutomationBreakdown:
    def test_computes_percentages_from_routed_by(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_search",
            json={
                "offset": 0, "total": 10,
                "hits": [
                    {"routed_by": "rule"},
                    {"routed_by": "rule"},
                    {"routed_by": "aito"},
                    {"routed_by": "aito"},
                    {"routed_by": "aito"},
                    {"routed_by": "aito"},
                    {"routed_by": "aito"},
                    {"routed_by": "human"},
                    {"routed_by": "human"},
                    {"routed_by": "none"},
                ],
            },
        )

        client = AitoClient(TEST_CONFIG)
        result = compute_automation_breakdown(client)

        assert result["total"] == 10
        assert result["rule"] == 2
        assert result["aito"] == 5
        assert result["human"] == 2
        assert result["none"] == 1
        assert result["rule_pct"] == 20
        assert result["aito_pct"] == 50
        assert result["automation_rate"] == 70

    def test_handles_empty_table(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_search",
            json={"offset": 0, "total": 0, "hits": []},
        )

        client = AitoClient(TEST_CONFIG)
        result = compute_automation_breakdown(client)

        assert result["total"] == 0
        assert result["automation_rate"] == 0


class TestComputeOverrideStats:
    def test_counts_by_field_and_corrector(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_search",
            json={
                "offset": 0, "total": 4,
                "hits": [
                    {"field": "gl_code", "corrected_by": "Sanna L."},
                    {"field": "gl_code", "corrected_by": "Mikael H."},
                    {"field": "gl_code", "corrected_by": "Sanna L."},
                    {"field": "approver", "corrected_by": "Tiina M."},
                ],
            },
        )

        client = AitoClient(TEST_CONFIG)
        result = compute_override_stats(client)

        assert result["total"] == 4
        assert result["by_field"]["gl_code"] == 3
        assert result["by_field"]["approver"] == 1
        assert result["by_corrector"]["Sanna L."] == 2
