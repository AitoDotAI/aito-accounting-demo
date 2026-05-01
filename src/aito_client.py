"""HTTP client for Aito's predictive database API.

Thin wrapper — each method maps directly to an Aito REST endpoint.
No abstraction beyond authentication and error handling. An outside
developer reading this file should see exactly what HTTP calls are
made and what response shapes come back.

Aito API docs: https://aito.ai/docs/api/
"""

from contextvars import ContextVar
from typing import Any

import httpx

from src.config import Config


# Per-request Aito-call accumulator. Set by the FastAPI middleware
# at the start of each HTTP request; read at the end so the response
# can carry X-Aito-Ms / X-Aito-Calls headers. Frontend uses these
# to render a persistent latency badge in the topbar — the demo's
# answer to "is the predictive layer actually fast?"
aito_call_log: ContextVar[list[float] | None] = ContextVar("aito_call_log", default=None)


class AitoError(Exception):
    """Raised when an Aito API call fails.

    Includes the HTTP status and response body so the caller has enough
    context to diagnose without a debugger.
    """

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class AitoClient:
    """Synchronous client for the Aito REST API."""

    def __init__(self, config: Config) -> None:
        self._base_url = config.aito_api_url
        self._headers = {
            "x-api-key": config.aito_api_key,
            "content-type": "application/json",
        }
        # Circuit breaker state — fail fast after 3 consecutive failures
        self._breaker_failures: int = 0
        self._breaker_open_until: float = 0.0
        self._breaker_last_error: str = ""

    def _record_failure(self, error: str) -> None:
        """Record a failure; trip the breaker after 3 in a row."""
        import time as _time
        self._breaker_failures += 1
        self._breaker_last_error = error
        if self._breaker_failures >= 3:
            self._breaker_open_until = _time.monotonic() + 30.0

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        """Make an HTTP request to Aito and return the parsed JSON response.

        Includes:
        - One retry on transient failures (5xx or connection error) with
          200ms backoff. Idempotent operations only — POST is also
          retried because Aito's _predict / _relate / _search are pure.
        - Circuit breaker: after 3 consecutive failures the breaker
          opens for 30 seconds; subsequent calls fail-fast with a
          helpful AitoError instead of waiting for timeouts.

        Raises AitoError on non-2xx status, connection failure, or
        when the circuit breaker is open.
        """
        import time as _time

        # Circuit breaker check
        if self._breaker_open_until > _time.monotonic():
            raise AitoError(
                f"Aito client circuit breaker is open (last error: "
                f"{self._breaker_last_error}). Will retry automatically; "
                f"wait a few seconds.",
                status_code=503,
            )

        last_exc: AitoError | None = None
        for attempt in range(2):  # original + 1 retry
            t0 = _time.monotonic()
            try:
                response = httpx.request(
                    method,
                    self._url(path),
                    headers=self._headers,
                    json=json,
                    timeout=120.0,
                )
            except httpx.HTTPError as exc:
                last_exc = AitoError(f"Aito request failed: {method} {path}: {exc}")
                if attempt == 0:
                    _time.sleep(0.2)
                    continue
                self._record_failure(str(exc))
                raise last_exc from exc

            if response.status_code >= 500 and attempt == 0:
                # Transient server error — retry once
                _time.sleep(0.2)
                continue

            if response.status_code >= 400:
                err = AitoError(
                    f"Aito returned {response.status_code} for {method} {path}: "
                    f"{response.text[:500]}",
                    status_code=response.status_code,
                    body=response.text,
                )
                if response.status_code >= 500:
                    self._record_failure(f"5xx: {response.status_code}")
                raise err

            # Success — reset breaker
            self._breaker_failures = 0
            # Record latency for the topbar badge (if a request-scoped
            # log was set up by the middleware).
            log = aito_call_log.get()
            if log is not None:
                log.append((_time.monotonic() - t0) * 1000.0)
            break

        return response.json()

    def get_schema(self) -> dict:
        """Fetch the database schema. Returns table definitions."""
        return self._request("GET", "/schema")

    def check_connectivity(self) -> bool:
        """Return True if the Aito instance is reachable and authenticated."""
        try:
            self.get_schema()
            return True
        except AitoError:
            return False

    def predict(self, table: str, where: dict, predict_field: str) -> dict:
        """Run a _predict query.

        Example:
            client.predict(
                table="invoices",
                where={"vendor": "Kesko Oyj", "amount": 4220},
                predict_field="gl_code",
            )

        Returns Aito response with hits like:
            {"$p": 0.91, "feature": "4400", "$why": {...}}

        Note: Aito returns the predicted value in "feature", not in a
        key named after the field.
        """
        # $why with highlight: per-factor returns the matched text
        # tokens wrapped in posPreTag/posPostTag so the UI can paint
        # the source words for Text fields like description. Without
        # `highlight` Aito only returns propositions like
        # {description: {$match: "monthly"}} -- with it, the response
        # also tells you which exact span matched.
        query = {
            "from": table,
            "where": where,
            "predict": predict_field,
            "select": [
                "$p",
                "feature",
                {"$why": {"highlight": {"posPreTag": "<mark>", "posPostTag": "</mark>"}}},
            ],
        }
        return self._request("POST", "/_predict", json=query)

    def relate(self, table: str, where: dict, relate_field: str) -> dict:
        """Run a _relate query to discover feature relationships.

        Example:
            client.relate(
                table="invoices",
                where={"routed": False},
                relate_field="gl_code",
            )

        Returns hits with rich statistics for each value of the
        related field:
            {
              "related": {"gl_code": {"$has": "4400"}},
              "condition": {"routed": {"$has": false}},
              "lift": 6.49,
              "fs": {"f": 33, "fOnCondition": 18, ...},
              "ps": {"p": 0.14, "pOnCondition": 0.95, ...}
            }

        Key fields in each hit:
        - related: the field value this row is about
        - lift: how much more likely this value is given the condition
        - fs.fOnCondition: count matching both condition and related value
        - fs.f: total count of this related value
        - ps.pOnCondition: probability of related value given condition
        """
        query = {
            "from": table,
            "where": where,
            "relate": relate_field,
        }
        return self._request("POST", "/_relate", json=query)

    def match(self, table: str, where: dict, match_field: str, limit: int = 5) -> dict:
        """Run a _match query to find records related to a context.

        Unlike _predict (which guesses a field value), _match finds
        which existing records best associate with the given context.
        Think of it as "recommendation" — given these features, which
        records are most relevant?

        Example:
            client.match(
                table="bank_transactions",
                where={"description": "KESKO OYJ", "amount": 4220},
                match_field="invoice_id",
            )

        Returns hits with the matched field value and $p score:
            {"$p": 0.056, "invoice_id": "INV-2628"}
        """
        query = {
            "from": table,
            "where": where,
            "match": match_field,
            "select": ["$p", "vendor", "invoice_id", "amount", "$why"],
            "limit": limit,
        }
        return self._request("POST", "/_match", json=query)

    def search(self, table: str, where: dict, limit: int = 10) -> dict:
        """Run a _search query to retrieve matching rows.

        Returns matching records from the specified table.
        """
        query = {
            "from": table,
            "where": where,
            "limit": limit,
        }
        return self._request("POST", "/_search", json=query)
