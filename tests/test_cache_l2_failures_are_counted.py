"""A broken L2 must not look exactly like a working one.

`cache.set`, `cache.get` and `cache.delete` treat the shared Aito table as
best-effort: an AitoError falls back to the in-process layer and the caller
never knows. That is the right behaviour for a request and the wrong one for
an operator, because a table that rejects every write and a table that works
produce identical responses. The failures are counted and /healthz and
/api/cache/status report them.
"""

import pytest
from fastapi.testclient import TestClient

import src.app as app_module
from src import cache
from src.aito_client import AitoError


class BrokenAito:
    """Every call fails, as an unreachable or refusing shared instance would."""

    def _request(self, method, path, json=None, **kwargs):
        raise AitoError(f"{method} {path} refused", status_code=503)

    def search(self, *args, **kwargs):
        raise AitoError("search refused", status_code=503)


class WorkingAito:
    def __init__(self):
        self.rows = []

    def _request(self, method, path, json=None, **kwargs):
        if path.startswith("/data/") and not path.endswith("_delete"):
            self.rows.append(json)
        return {}

    def search(self, *args, **kwargs):
        return {"hits": []}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(cache, "_l2_failures", {"writes": 0, "deletes": 0, "reads": 0})
    monkeypatch.setattr(cache, "_l2_last_error", None)
    cache._l1.clear()
    yield
    cache._l1.clear()


def test_a_working_l2_reports_no_failures(monkeypatch):
    monkeypatch.setattr(cache, "_aito", WorkingAito())

    cache.set("k", {"v": 1})
    cache.get("other")
    cache.delete("k")

    health = cache.l2_health()
    assert health["configured"] is True
    assert health["failed_writes"] == health["failed_deletes"] == health["failed_reads"] == 0
    assert health["last_error"] is None


def test_a_failing_write_is_counted_and_the_value_still_serves_from_l1(monkeypatch):
    monkeypatch.setattr(cache, "_aito", BrokenAito())

    cache.set("k", {"v": 1})

    assert cache.get("k") == {"v": 1}, "the request path must not change"
    health = cache.l2_health()
    assert health["failed_writes"] == 1
    assert "refused" in health["last_error"]


def test_failing_reads_and_deletes_are_counted_too(monkeypatch):
    monkeypatch.setattr(cache, "_aito", BrokenAito())

    cache.get("never-written")
    cache.delete("k")

    health = cache.l2_health()
    assert health["failed_reads"] == 1
    assert health["failed_deletes"] >= 1


def test_a_local_only_set_is_not_an_l2_attempt(monkeypatch):
    monkeypatch.setattr(cache, "_aito", BrokenAito())

    cache.set("k", {"v": 1}, local_only=True)

    assert cache.l2_health()["failed_writes"] == 0


def test_no_l2_registered_is_reported_as_not_configured(monkeypatch):
    monkeypatch.setattr(cache, "_aito", None)

    assert cache.l2_health()["configured"] is False


def test_healthz_and_cache_status_carry_the_l2_counts(monkeypatch):
    monkeypatch.setattr(cache, "_aito", BrokenAito())
    cache.set("k", {"v": 1})
    client = TestClient(app_module.app)

    assert client.get("/healthz").json()["l2"]["failed_writes"] == 1
    status = client.get("/api/cache/status", params={"customer_id": "CUST-0000"}).json()
    assert status["l2"]["failed_writes"] == 1
