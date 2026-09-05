"""HTTP client for the Aito **v2** API.

Kept separate from `AitoClient` (v1) on purpose. v2 is a different API,
not a version bump:

- **One query endpoint.** Every query type (`predict`, `relate`,
  `recommend`, plain search) is a top-level key inside a single
  `POST /api/v2/_query` body, instead of v1's verb-per-endpoint.
- **Collections vs legacy tables.** v2 introduces "collections" (its
  native table type) alongside "legacy tables" (anything uploaded via
  v1). Predictive features like `relate`/`$patterns` run on collections
  only — on a legacy table they return HTTP 501.
- **Environments in the URL path.** A branched environment is addressed
  as `/db/<db>/env/<env-name>/api/v2/...`. There is no env-scoped key —
  env auth is database-scoped, so the master key authorizes every env.
  Omit the `/env/<name>` segment to talk to master.

Keeping v2 in its own file lets a reader see the whole v2 surface at
once. The v1 client stays untouched so the live v1 demo keeps working.

Aito v2 API docs: https://aito.ai/docs/api/v2/
"""

from typing import Any

import httpx

from src.aito_client import (
    AitoError,
    _path_is_user_facing,
    _semaphore_for,
    aito_call_log,
)


class AitoV2Error(AitoError):
    """Raised when an Aito v2 API call fails.

    Subclasses `AitoError` so the v2 client is a genuine drop-in: existing
    `except AitoError` handlers (in the rule-mining service and the API
    endpoints) catch v2 failures too. Carries the HTTP status and response
    body so a caller can diagnose without a debugger.
    """


def resolve_env(value: str | None) -> tuple[bool, str | None]:
    """Interpret `AITO_V2_ENV` into (use_v2, environment or None).

        unset / blank  -> (False, None)   v1, the production default
        "<name>"       -> (True, "<name>")  v2 against that env branch
        "master"       -> (True, None)      v2 against master, unscoped

    `master` is a sentinel, not an env. The API refuses `/env/master/`
    outright — "Env 'master' is the default; use the unscoped /api/...
    path" — so the one name that cannot denote a branch is free to mean
    "no branch". That is the end state of a v2 cutover: the env is
    promoted into master and the app stops pointing at a branch.
    Without it, v2-against-master cannot be expressed at all.
    """
    name = (value or "").strip()
    if not name:
        return False, None
    if name.lower() in ("master", "env.master"):
        return True, None
    return True, name


class AitoV2Client:
    """Synchronous client for the Aito v2 REST API.

    Args:
        base_url: the database base, e.g.
            ``https://shared.aito.ai/db/aito-accounting-demo`` (no
            ``/api/...`` suffix).
        api_key: the master API key (also authorizes env access).
        env: optional environment name to address, e.g. ``env.v2-demo``.
            When set, every call is routed through the ``/env/<env>``
            path segment. When ``None``, calls hit the master env.
    """

    def __init__(self, base_url: str, api_key: str, env: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._env = env
        # Pooled client keeps the TCP+TLS connection alive across calls,
        # the same reason the v1 client pools — a fresh connection per
        # request pays ~150 ms of handshake every time on a shared host.
        self._client = httpx.Client(
            headers={"x-api-key": api_key, "content-type": "application/json"}
        )

    def _url(self, path: str) -> str:
        # v2 addresses an environment as two path segments `/env/<name>`
        # (NOT a dotted `env.<name>` in place of the db — that never
        # matches the route and falls through to a misleading 403).
        env_segment = f"/env/{self._env}" if self._env else ""
        return f"{self._base_url}{env_segment}/api/v2{path}"

    def _request(
        self,
        method: str,
        path: str,
        json: Any | None = None,
        timeout: float | None = 120.0,
    ) -> Any:
        """Make an HTTP request to Aito v2 and return the parsed JSON.

        Retries once on a transient 5xx or connection error with a short
        backoff. Raises AitoV2Error on any non-2xx status.

        Shares the v1 client's process-wide concurrency semaphores. A v2
        environment lives on the *same* Aito instance as master, so the
        caps have to be global to the process, not per-client — otherwise
        a v2 build doubles the in-flight load on the shared server the
        live v1 demo is also using. `/_evaluate` lands on its own size-1
        semaphore for the same reason it does in v1: it is the
        memory-heavy path.
        """
        import time as _time

        last_exc: AitoV2Error | None = None
        for attempt in range(2):  # original + 1 retry
            t0 = _time.monotonic()
            try:
                with _semaphore_for(path):
                    response = self._client.request(
                        method, self._url(path), json=json, timeout=timeout
                    )
            except httpx.HTTPError as exc:
                last_exc = AitoV2Error(f"Aito v2 request failed: {method} {path}: {exc}")
                if attempt == 0:
                    _time.sleep(0.2)
                    continue
                raise last_exc from exc

            if response.status_code >= 500 and attempt == 0:
                _time.sleep(0.2)
                continue

            # Feed the same request-scoped accumulator the v1 client
            # feeds, so the topbar latency badge keeps working when the
            # app is pointed at v2. Prefer Aito's server-side timing
            # header over wall-clock, for the reason given in the v1
            # client: wall-clock includes RTT, TLS, and semaphore wait.
            log = aito_call_log.get()
            if log is not None and _path_is_user_facing(path):
                header_ms = response.headers.get("x-aitoai-response-time")
                try:
                    ms = float(header_ms) if header_ms else (_time.monotonic() - t0) * 1000.0
                except ValueError:
                    ms = (_time.monotonic() - t0) * 1000.0
                log.append((path, ms))

            if response.status_code >= 400:
                raise AitoV2Error(
                    f"Aito v2 returned {response.status_code} for {method} {path}: "
                    f"{response.text[:500]}",
                    status_code=response.status_code,
                    body=response.text,
                )
            return response.json()

    # --- Environments --------------------------------------------------

    def list_envs(self) -> dict:
        """List environments. Returns ``{"envs": [{"name", "isMaster"}]}``."""
        return self._request("GET", "/_envs")

    def branch_env(self, name: str) -> dict:
        """Branch a new environment off master.

        Returns ``{"basedOn": "env.master", "name": name, "status": "created"}``.
        Branching returns no key — the master key authorizes the new env.
        """
        return self._request("POST", "/_envs", json={"name": name})

    def delete_env(self, name: str) -> dict:
        """Delete an environment."""
        return self._request("DELETE", f"/_envs/{name}")

    # --- Schema (collections) -----------------------------------------

    def get_schema(self, table: str | None = None) -> dict:
        """Fetch the schema for the whole db or one table/collection.

        Note: `GET /schema/<name>` does not currently echo back `link`
        or `analyzer` column options even though they are applied — do
        not rely on it for full round-trip verification.
        """
        return self._request("GET", f"/schema/{table}" if table else "/schema")

    def create_collection(self, name: str, columns: dict) -> dict:
        """Create a v2 collection.

        `columns` is the same column map used by the v1 schema (types
        String/Text/Decimal/Int/Boolean, plus `link`/`nullable`), so a
        v1 table schema translates by swapping `type: table` for the
        collection creation here.
        """
        body = {"type": "collection", "columns": columns}
        return self._request("PUT", f"/schema/{name}", json=body)

    def delete_collection(self, name: str) -> dict:
        """Delete a collection (or legacy table) and its data."""
        return self._request("DELETE", f"/schema/{name}")

    # --- Data ----------------------------------------------------------

    def insert_batch(self, name: str, rows: list[dict], batch_size: int = 1000) -> int:
        """Insert rows into a collection in chunks. Returns the count inserted."""
        total = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            result = self._request("POST", f"/data/{name}/batch", json=chunk)
            total += int(result.get("count", len(chunk)))
        return total

    def relate_features(
        self,
        table: str,
        population_where: dict,
        target: dict,
        relate_fields: list[str],
    ) -> dict:
        """Relate features to a target within a sub-population (ADR 0015 diagnostic).

        Drop-in for the v1 client's `relate_features`, returning the same hit
        shape (`related` dict, `lift`, `fs.f` / `fs.fOnCondition`) so
        `interpret_diagnosis` works unchanged.

        The relate condition is the `$on` proposition "target GIVEN population".
        v2 returns each feature value with `lift` and `fs` (`f`, `fOnCondition`),
        including the *exception* values that never co-occur with the target —
        the same shape v1 returns — so `interpret_diagnosis` consumes it directly.
        """
        return self.query(
            {
                "from": table,
                "where": {"$on": [target, population_where]},
                "relate": relate_fields,
                "select": ["related", "lift", "fs"],
                "orderBy": "lift",
            }
        )

    def optimize(self, name: str) -> dict:
        """Rebuild a collection's index after a bulk load.

        Required for prediction quality: on a freshly bulk-loaded
        collection, `predict` returns degraded/near-flat posteriors until
        this runs (verified: an EEE-vendor invoice predicts a wrong GL at
        ~0.19 before optimize, the correct GL at 0.63+ after). Notably,
        `relate`/`$patterns` on the same un-optimized collection are already
        correct — only predict needs the rebuilt index. Mirrors the v1
        loader's optimize step.
        """
        return self._request("POST", f"/data/{name}/optimize", json={})

    # --- Queries -------------------------------------------------------

    def check_connectivity(self) -> bool:
        """Return True if the env is reachable and authenticated.

        Mirrors the v1 client's probe — a tiny query rather than
        `/schema`, because `/schema` on a degraded instance can hang for
        the full client timeout while a one-row read still answers.
        """
        try:
            self.query({"from": "customers", "limit": 1})
            return True
        except AitoError:
            return False

    def query(self, body: dict) -> dict:
        """Run a raw Query2 body against `POST /_query`.

        The envelope is ``{offset, total, hits: [...]}``.
        """
        return self._request("POST", "/_query", json=body)

    def search(self, table: str, where: dict, limit: int = 10) -> dict:
        """Retrieve matching rows (v2 has no separate `_search`; it's `_query`).

        Returns ``{offset, total, hits}`` — the same envelope callers use to
        read `total` (for exact counts with ``limit=0``) or iterate `hits`.
        """
        return self.query({"from": table, "where": where, "limit": limit})

    # Highlight tags for `$why` on Text fields — the frontend paints the
    # matched tokens (same request the v1 client makes).
    _WHY_SELECT = {"$why": {"highlight": {"posPreTag": "<mark>", "posPostTag": "</mark>"}}}

    def predict(self, table: str, where: dict, predict_field: str, limit: int = 50) -> dict:
        """Run a prediction, shaped as a v1 `_predict` response (drop-in).

        Signature and response match the v1 client: v2 returns the predicted
        value in ``$value``, which we alias to ``feature`` so callers written
        against v1 (and `_extract_alternatives`) work unchanged. ``$why`` is
        the same nested factor tree v1 returns — already parsed by
        `invoice_service._extract_why_factors` — including highlight spans.

        `limit` bounds the returned candidate values (default returns only ~10,
        so we lift it to cover a target field's full value set).
        """
        response = self.query(
            {"from": table, "where": where, "predict": predict_field,
             "select": ["$p", "$value", self._WHY_SELECT], "limit": limit}
        )
        for hit in response.get("hits", []):
            hit.setdefault("feature", hit.get("$value"))
        return response

    def evaluate(self, body: dict, timeout: float | None = 600.0) -> dict:
        """Run cross-validation, shaped as a v1 `_evaluate` response (drop-in).

        v2 keeps `_evaluate` as its own endpoint — it is *not* a `_query`
        key (the Query2 grammar rejects one). The request body is the v1
        body unchanged (`testSource` + `evaluate` + optional `select`).

        Two response differences are normalized here so the quality
        dashboard and the per-case diff table read it unchanged:

        1. v2 wraps the metrics in an envelope, ``{"kind": "evaluation",
           "data": {...}}``; v1 returns them at the top level.
        2. Inside `cases[]`, the predicted value moved from `feature` to
           `$value` (the same rename `predict` got).

        v2's metric set is a superset of v1's — every key the app reads
        (`accuracy`, `baseAccuracy`, `geomMeanP`, `testSamples`,
        `trainSamples`, `accuracyGain`, `meanRank`) is present, alongside
        new ones (`logLoss`, `brierScore`, `ece`, `mrr`).

        The default timeout is 10 min: a 30-row evaluation over 128 k
        training rows takes ~60 s, and the dashboard runs larger samples.
        """
        response = self._request("POST", "/_evaluate", json=body, timeout=timeout)
        metrics = response.get("data", response)
        for case in metrics.get("cases", []):
            for slot in ("top", "correct"):
                entry = case.get(slot)
                if isinstance(entry, dict):
                    entry.setdefault("feature", entry.get("$value"))
        return metrics

    def relate(self, table: str, where: dict, relate_field: str) -> dict:
        """Single-field `_relate` — drop-in for the v1 client.

        v2 returns each hit's `related` as `{field: value}`; we wrap the value
        as `{field: {"$has": value}}` to match the v1 shape callers read
        directly. `fs` (with `fOnCondition` / `fCondition`) is already returned.
        """
        response = self.query(
            {"from": table, "where": where, "relate": [relate_field],
             "select": ["related", "condition", "lift", "fs"], "orderBy": "lift"}
        )
        for hit in response.get("hits", []):
            related = hit.get("related")
            if isinstance(related, dict):
                hit["related"] = {
                    field: value if isinstance(value, dict) else {"$has": value}
                    for field, value in related.items()
                }
        return response

    def relate_patterns(
        self,
        table: str,
        target: dict,
        candidate_fields: list[str],
        where_filter: dict | None = None,
        k: int = 8,
        limit: int = 8,
    ) -> dict:
        """Mine AND-conjunction rules with `relate` + `$patterns`.

        Signature matches the v1 client's `relate_patterns`, so it is a
        drop-in for the rule-mining service. Runs on **collections only** (a
        legacy table returns 501). `where_filter` scopes the population via a
        nested `from` (e.g. `{"customer_id": ...}` for multi-tenancy), exactly
        as in v1.

        v2 returns each hit's `related` / `condition` as a structured
        proposition (`{"$and": [{field: value}, …]}`), which `parse_conjunction`
        already understands, so no post-processing is needed. Support counts are
        recomputed exactly by the caller (they don't rely on `$patterns`' stats).
        """
        from_clause: Any = (
            {"from": table, "where": where_filter} if where_filter else table
        )
        return self.query(
            {
                "from": from_clause,
                "where": target,
                "relate": {
                    "$patterns": {
                        "$related": {"relate": candidate_fields, "k": k, "to": target}
                    }
                },
                "select": ["related", "condition", "lift"],
                "orderBy": "lift",
                "limit": limit,
            }
        )
