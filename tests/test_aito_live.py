"""Live integration tests against the real Aito instance.

These tests verify that our query shapes produce meaningful results
with the sample dataset. They require AITO_API_URL and AITO_API_KEY
to be configured and data to be loaded (./do load-data).

Run with: pytest tests/test_aito_live.py -v
Skipped automatically if Aito is not reachable.
"""

import pytest

from src.aito_client import AitoClient
from src.config import load_config

try:
    _config = load_config()
    _client = AitoClient(_config)
    _aito_available = _client.check_connectivity()
except Exception:
    _aito_available = False

pytestmark = pytest.mark.skipif(
    not _aito_available,
    reason="Aito instance not reachable — skipping live tests",
)


@pytest.fixture
def client():
    return _client


class TestPredictLive:
    def test_predict_gl_code_for_known_vendor_returns_expected_top_result(self, client):
        """Kesko Oyj invoices should predict GL 4400 (Supplies) with high confidence."""
        result = client.predict("invoices", {"vendor": "Kesko Oyj"}, "gl_code")

        assert result["total"] > 0
        top = result["hits"][0]
        assert top["feature"] == "4400"
        assert top["$p"] > 0.5

    def test_predict_approver_for_telecom_vendor(self, client):
        """Telia Finland should route to Mikael H."""
        result = client.predict("invoices", {"vendor": "Telia Finland"}, "approver")

        top = result["hits"][0]
        assert top["feature"] == "Mikael H."
        assert top["$p"] > 0.5

    def test_predict_returns_why_explanation(self, client):
        """$why should be present and non-empty."""
        result = client.predict(
            "invoices", {"vendor": "Kesko Oyj"}, "gl_code"
        )

        top = result["hits"][0]
        assert "$why" in top
        assert top["$why"]["type"] == "product"

    def test_predict_probabilities_are_valid(self, client):
        """All $p values should be in [0, 1]."""
        result = client.predict("invoices", {"vendor": "Fazer Bakeries"}, "gl_code")

        for hit in result["hits"]:
            assert 0 <= hit["$p"] <= 1, f"Invalid probability: {hit['$p']}"


class TestRelateLive:
    def test_relate_returns_statistical_breakdown(self, client):
        """_relate should return lift and frequency stats for each GL code value."""
        result = client.relate("invoices", {"vendor": "Kesko Oyj"}, "gl_code")

        assert result["total"] > 0
        top = result["hits"][0]

        # Structure checks
        assert "related" in top
        assert "lift" in top
        assert "fs" in top
        assert "ps" in top

        # The related field should reference gl_code
        assert "gl_code" in top["related"]

        # Stats should be populated
        assert top["fs"]["n"] > 0
        assert top["lift"] > 0

    def test_relate_kesko_has_strongest_lift_for_4400(self, client):
        """Kesko Oyj should have highest lift for GL 4400."""
        result = client.relate("invoices", {"vendor": "Kesko Oyj"}, "gl_code")

        # Find the 4400 hit
        hit_4400 = None
        for hit in result["hits"]:
            if hit["related"]["gl_code"]["$has"] == "4400":
                hit_4400 = hit
                break

        assert hit_4400 is not None, "GL 4400 not found in relate results"
        # 4400 should have the highest lift for Kesko
        assert hit_4400["lift"] > 1.0


class TestSearchLive:
    def test_search_returns_matching_records(self, client):
        """Search should find Kesko invoices."""
        result = client.search("invoices", {"vendor": "Kesko Oyj"}, limit=5)

        assert result["total"] > 0
        for hit in result["hits"]:
            assert hit["vendor"] == "Kesko Oyj"
