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

from src.aito_client import AitoError


class AitoV2Error(AitoError):
    """Raised when an Aito v2 API call fails.

    Subclasses `AitoError` so the v2 client is a genuine drop-in: existing
    `except AitoError` handlers (in the rule-mining service and the API
    endpoints) catch v2 failures too. Carries the HTTP status and response
    body so a caller can diagnose without a debugger.
    """


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
        """
        import time as _time

        last_exc: AitoV2Error | None = None
        for attempt in range(2):  # original + 1 retry
            try:
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

    def predict(
        self,
        table: str,
        where: dict,
        predict_field: str,
        *,
        explain: bool = False,
        limit: int = 5,
    ) -> dict:
        """Run a prediction via the unified `_query`.

        In v2 the predicted value comes back in ``$value`` (v1 used
        ``feature``). With ``explain=True`` the hit also carries ``$why``,
        which in v2 is a nested factor tree rather than v1's flat list.
        """
        select = ["$p", "$value"] + (["$why"] if explain else [])
        return self.query(
            {"from": table, "where": where, "predict": predict_field,
             "select": select, "limit": limit}
        )

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
