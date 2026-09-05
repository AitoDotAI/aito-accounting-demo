"""Tests for the Aito v2 client's request construction.

`AitoV2Client` is a thin wrapper over the unified `_query` endpoint. The
two things worth pinning are (1) how an environment is addressed in the URL
path, and (2) the Query2 bodies it builds for rule mining — both were the
non-obvious parts of the v2 migration. These are pure (no network): the URL
tests read `_url`, the body tests capture what would be sent.
"""

from src.aito_v2_client import AitoV2Client, resolve_env


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
        # The migration's main gotcha: an env is `/env/<name>/`, not a
        # dotted name in place of the db. Note the name carries no `env.`
        # prefix — that prefix is reserved and rejected at request time.
        assert _client("v2-demo")._url("/_query") == (
            "https://shared.aito.ai/db/aito-accounting-demo/env/v2-demo/api/v2/_query"
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


class _CannedRequestClient(AitoV2Client):
    """Returns a fixed `_request` response, to test `evaluate` normalization."""

    def __init__(self, response):
        self._base_url = "https://h/db/x"
        self._env = None
        self._response = response
        self.path = None

    def _request(self, method, path, json=None, timeout=120.0):
        self.path = path
        return self._response


class TestEvaluateDropIn:
    """v2 keeps `_evaluate` as its own endpoint, but reshapes the response.

    The quality dashboard reads v1's flat metrics and `cases[].top.feature`,
    so `evaluate()` unwraps the envelope and re-aliases the value.
    """

    def _client(self):
        return _CannedRequestClient({
            "kind": "evaluation",
            "data": {
                "accuracy": 0.57,
                "baseAccuracy": 0.17,
                "cases": [
                    {"accurate": True,
                     "top": {"$value": "4400", "$p": 0.98},
                     "correct": {"$value": "4400", "$p": 0.98, "rank": 0}},
                ],
            },
        })

    def test_unwraps_the_evaluation_envelope(self):
        client = self._client()
        out = client.evaluate({"testSource": {}, "evaluate": {}})
        # v1 returns metrics at the top level; v2 nests them under `data`.
        assert out["accuracy"] == 0.57
        assert out["baseAccuracy"] == 0.17

    def test_aliases_case_value_to_feature(self):
        client = self._client()
        out = client.evaluate({"testSource": {}, "evaluate": {}})
        case = out["cases"][0]
        assert case["top"]["feature"] == "4400"
        assert case["correct"]["feature"] == "4400"

    def test_posts_to_the_evaluate_endpoint_not_query(self):
        client = self._client()
        client.evaluate({"testSource": {}, "evaluate": {}})
        # `_evaluate` is not a Query2 key — the grammar rejects one.
        assert client.path == "/_evaluate"


class TestResolveEnv:
    """How `AITO_V2_ENV` decides which API generation, and where.

    This is the switch a production cutover turns. The end state of one
    is v2 reading master directly — the env has been promoted and the
    app should stop pointing at a branch — and that state was not
    expressible until `master` became a sentinel here.
    """

    def test_unset_means_v1(self):
        assert resolve_env(None) == (False, None)
        assert resolve_env("") == (False, None)

    def test_whitespace_is_not_a_v2_opt_in(self):
        # `AITO_V2_ENV=` in a deploy config must not silently switch
        # production onto a different API generation.
        assert resolve_env("   ") == (False, None)

    def test_a_name_selects_that_environment(self):
        assert resolve_env("v2-demo") == (True, "v2-demo")

    def test_master_means_v2_with_no_env_segment(self):
        # Not an env named "master": the API refuses /env/master/, so the
        # name is free to mean "unscoped".
        assert resolve_env("master") == (True, None)

    def test_the_env_prefixed_form_of_master_too(self):
        assert resolve_env("env.master") == (True, None)
        assert resolve_env("MASTER") == (True, None)

    def test_master_resolves_to_the_unscoped_url(self):
        _, target = resolve_env("master")
        assert _client(target)._url("/_query") == (
            "https://shared.aito.ai/db/aito-accounting-demo/api/v2/_query"
        )
