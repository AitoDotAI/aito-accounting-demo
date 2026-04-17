"""HTTP client for Aito's predictive database API.

Thin wrapper — each method maps directly to an Aito REST endpoint.
No abstraction beyond authentication and error handling. An outside
developer reading this file should see exactly what HTTP calls are
made and what response shapes come back.

Aito API docs: https://aito.ai/docs/api/
"""

from typing import Any

import httpx

from src.config import Config


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

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        """Make an HTTP request to Aito and return the parsed JSON response.

        Raises AitoError on non-2xx status or connection failure.
        """
        try:
            response = httpx.request(
                method,
                self._url(path),
                headers=self._headers,
                json=json,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise AitoError(
                f"Aito request failed: {method} {path}: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise AitoError(
                f"Aito returned {response.status_code} for {method} {path}: "
                f"{response.text[:500]}",
                status_code=response.status_code,
                body=response.text,
            )

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
                predict_field="GLCode",
            )

        Returns the full Aito response including $p scores.
        """
        query = {
            "from": table,
            "where": where,
            "predict": predict_field,
            "select": ["$p", predict_field, "$why"],
        }
        return self._request("POST", "/_predict", json=query)

    def relate(self, table: str, where: dict, relate_field: str) -> dict:
        """Run a _relate query to discover feature relationships.

        Example:
            client.relate(
                table="invoices",
                where={"routed": False},
                relate_field="GLCode",
            )

        Returns features correlated with the target field, with lift
        and probability scores.
        """
        query = {
            "from": table,
            "where": where,
            "relate": relate_field,
            "select": ["feature", "$p", "lift"],
        }
        return self._request("POST", "/_relate", json=query)

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
