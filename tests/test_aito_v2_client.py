"""Tests for the Aito v2 client's request construction.

`AitoV2Client` is a thin wrapper over the unified `_query` endpoint. The
two things worth pinning are (1) how an environment is addressed in the URL
path, and (2) the Query2 bodies it builds for rule mining — both were the
non-obvious parts of the v2 migration. These are pure (no network): the URL
tests read `_url`, the body tests capture what would be sent.
"""

from src.aito_v2_client import AitoV2Client


def _client(env=None):
    """An AitoV2Client without the HTTP setup, for URL/body inspection."""
    client = AitoV2Client.__new__(AitoV2Client)
    client._base_url = "https://shared.aito.ai/db/aito-accounting-demo"
    client._env = env
    return client


class TestEnvAddressing:
    def test_master_url_has_no_env_segment(self):
        assert _client()._url("/_query") == (
            "https://shared.aito.ai/db/aito-accounting-demo/api/v2/_query"
        )

    def test_env_is_addressed_as_a_path_segment(self):
        # The migration's main gotcha: an env is `/env/<full-name>/`, not a
        # dotted name in place of the db.
        assert _client("env.v2-demo")._url("/_query") == (
            "https://shared.aito.ai/db/aito-accounting-demo/env/env.v2-demo/api/v2/_query"
        )


class _CapturingClient(AitoV2Client):
    """Captures the body that would be POSTed, instead of making a request."""

    def __init__(self):
        self._base_url = "https://h/db/x"
        self._env = None
        self.body = None

    def _request(self, method, path, json=None, timeout=120.0):
        self.body = json
        return {"hits": [], "total": 0}


class TestQueryBodies:
    def test_relate_patterns_scopes_with_nested_from_and_mines_target(self):
        client = _CapturingClient()
        client.relate_patterns(
            "invoices", {"gl_code": "1600"}, ["vendor", "category"],
            where_filter={"customer_id": "C"}, k=6, limit=5,
        )
        assert client.body["from"] == {"from": "invoices", "where": {"customer_id": "C"}}
        assert client.body["where"] == {"gl_code": "1600"}
        assert client.body["relate"] == {
            "$patterns": {"$related": {"relate": ["vendor", "category"], "k": 6,
                                       "to": {"gl_code": "1600"}}}
        }
        assert client.body["orderBy"] == "lift" and client.body["limit"] == 5

    def test_relate_features_is_a_conditional_on_relate(self):
        client = _CapturingClient()
        client.relate_features("invoices", {"vendor": "X"}, {"gl_code": "1600"}, ["amount_band"])
        # "target GIVEN the rule's population" — the diagnostic condition.
        assert client.body["where"] == {"$on": [{"gl_code": "1600"}, {"vendor": "X"}]}
        assert client.body["relate"] == ["amount_band"]
        assert "fs" in client.body["select"]

    def test_search_count_uses_limit_zero(self):
        client = _CapturingClient()
        client.search("invoices", {"customer_id": "C"}, limit=0)
        assert client.body == {"from": "invoices", "where": {"customer_id": "C"}, "limit": 0}


class _CannedQueryClient(AitoV2Client):
    """Returns a fixed `query` response, to test predict/relate post-processing."""

    def __init__(self, response):
        self._base_url = "https://h/db/x"
        self._env = None
        self._response = response
        self.body = None

    def query(self, body):
        self.body = body
        return self._response


class TestPredictDropIn:
    def test_aliases_value_to_feature_and_requests_why(self):
        client = _CannedQueryClient({"hits": [{"$p": 0.9, "$value": "4400", "$why": {}}]})
        out = client.predict("invoices", {"vendor": "X"}, "gl_code")
        # v2's `$value` is exposed as `feature` for v1-shaped consumers.
        assert out["hits"][0]["feature"] == "4400"
        assert client.body["predict"] == "gl_code"
        assert any(isinstance(s, dict) and "$why" in s for s in client.body["select"])


class TestRelateDropIn:
    def test_wraps_related_value_in_has(self):
        client = _CannedQueryClient(
            {"hits": [{"related": {"gl_code": "4400"}, "fs": {"fOnCondition": 3, "fCondition": 3}}]}
        )
        out = client.relate("invoices", {"vendor": "X"}, "gl_code")
        # v2 returns {field: value}; callers expect the v1 {field: {$has: value}}.
        assert out["hits"][0]["related"] == {"gl_code": {"$has": "4400"}}
