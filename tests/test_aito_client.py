"""Tests for the Aito HTTP client.

Each test shows a concrete Aito request/response pair — these double
as documentation for how the Aito API works.
"""

import pytest
import httpx

from src.aito_client import AitoClient, AitoError
from src.config import Config

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)


def make_client() -> AitoClient:
    return AitoClient(TEST_CONFIG)


class TestGetSchema:
    def test_returns_schema_on_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/schema",
            json={"schema": {"invoices": {"type": "table"}}},
        )

        result = make_client().get_schema()

        assert result == {"schema": {"invoices": {"type": "table"}}}

    def test_raises_on_auth_failure(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/schema",
            status_code=401,
            text="Unauthorized",
        )

        with pytest.raises(AitoError, match="401"):
            make_client().get_schema()

    def test_raises_on_connection_error(self, httpx_mock):
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://test.aito.app/db/demo/api/v1/schema",
        )

        with pytest.raises(AitoError, match="Connection refused"):
            make_client().get_schema()


class TestCheckConnectivity:
    def test_returns_true_when_reachable(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/schema",
            json={"schema": {}},
        )

        assert make_client().check_connectivity() is True

    def test_returns_false_when_unreachable(self, httpx_mock):
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://test.aito.app/db/demo/api/v1/schema",
        )

        assert make_client().check_connectivity() is False


class TestPredict:
    def test_predict_sends_correct_query_and_parses_response(self, httpx_mock):
        """Aito _predict returns {$p, feature, $why} per hit."""
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={
                "offset": 0,
                "total": 2,
                "hits": [
                    {"$p": 0.91, "feature": "4400", "$why": {"type": "product"}},
                    {"$p": 0.03, "feature": "6200", "$why": {"type": "product"}},
                ],
            },
        )

        result = make_client().predict(
            table="invoices",
            where={"vendor": "Kesko Oyj", "amount": 4220},
            predict_field="gl_code",
        )

        assert result["hits"][0]["$p"] == 0.91
        assert result["hits"][0]["feature"] == "4400"

        # Verify the query shape sent to Aito
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["from"] == "invoices"
        assert body["predict"] == "gl_code"
        assert "feature" in body["select"]
        assert "$p" in body["select"]

    def test_predict_raises_on_server_error(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            status_code=500,
            text="Internal Server Error",
        )

        with pytest.raises(AitoError, match="500"):
            make_client().predict(
                table="invoices",
                where={"vendor": "Test"},
                predict_field="gl_code",
            )


class TestRelate:
    def test_relate_returns_statistical_relationships(self, httpx_mock):
        """Aito _relate returns rich stats: related value, lift, counts, probabilities."""
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_relate",
            json={
                "offset": 0,
                "total": 2,
                "hits": [
                    {
                        "related": {"gl_code": {"$has": "4400"}},
                        "condition": {"routed": {"$has": False}},
                        "lift": 6.49,
                        "fs": {"f": 33, "fOnCondition": 18, "fOnNotCondition": 15, "fCondition": 18, "n": 230},
                        "ps": {"p": 0.14, "pOnCondition": 0.95, "pOnNotCondition": 0.07, "pCondition": 0.08},
                    },
                    {
                        "related": {"gl_code": {"$has": "6100"}},
                        "condition": {"routed": {"$has": False}},
                        "lift": 0.51,
                        "fs": {"f": 67, "fOnCondition": 0, "fOnNotCondition": 67, "fCondition": 18, "n": 230},
                        "ps": {"p": 0.29, "pOnCondition": 0.15, "pOnNotCondition": 0.30, "pCondition": 0.08},
                    },
                ],
            },
        )

        result = make_client().relate(
            table="invoices",
            where={"routed": False},
            relate_field="gl_code",
        )

        assert len(result["hits"]) == 2
        assert result["hits"][0]["lift"] == 6.49
        assert result["hits"][0]["related"]["gl_code"]["$has"] == "4400"
        assert result["hits"][0]["fs"]["fOnCondition"] == 18

        # Verify query shape
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["from"] == "invoices"
        assert body["relate"] == "gl_code"


class TestSearch:
    def test_search_with_limit(self, httpx_mock):
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_search",
            json={
                "offset": 0,
                "total": 47,
                "hits": [{"vendor": "Kesko Oyj", "amount": 4220}],
            },
        )

        result = make_client().search(
            table="invoices",
            where={"vendor": "Kesko Oyj"},
            limit=5,
        )

        assert result["total"] == 47

        import json

        body = json.loads(httpx_mock.get_request().content)
        assert body["limit"] == 5
