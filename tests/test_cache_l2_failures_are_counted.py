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
    assert health["last_error"] == "AitoError status=503 write /data/cache_entries"


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


class DeleteOnlyBroken(WorkingAito):
    """The delete-before-insert fails; the insert itself works."""

    def _request(self, method, path, json=None, **kwargs):
        if path == "/data/_delete":
            raise AitoError("delete refused", status_code=503)
        return super()._request(method, path, json=json, **kwargs)


def test_the_delete_before_insert_inside_set_is_counted(monkeypatch):
    monkeypatch.setattr(cache, "_aito", DeleteOnlyBroken())

    cache.set("k", {"v": 1})

    health = cache.l2_health()
    assert health["failed_deletes"] == 1 and health["failed_writes"] == 0


def test_only_the_first_failure_of_each_kind_is_logged(monkeypatch, capsys):
    monkeypatch.setattr(cache, "_aito", BrokenAito())

    for i in range(5):
        cache.set(f"k{i}", {"v": i})

    lines = [l for l in capsys.readouterr().err.splitlines() if "first failed L2 write" in l]
    assert len(lines) == 1, f"{len(lines)} log lines for 5 failures"
    assert cache.l2_health()["failed_writes"] == 5


class LeakyAito(BrokenAito):
    def _request(self, method, path, json=None, **kwargs):
        raise AitoError(f"{method} {path} failed",
                        status_code=500, body='{"secret": "SECRET-ROW-CONTENT"}')


def test_the_public_health_report_carries_no_error_body(monkeypatch, capsys):
    monkeypatch.setattr(cache, "_aito", LeakyAito())
    cache.set("k", {"v": 1})
    log = capsys.readouterr().err
    client = TestClient(app_module.app)

    body = client.get("/healthz").text

    assert "SECRET-ROW-CONTENT" not in body, "the public endpoint serves an Aito error body"
    last = client.get("/healthz").json()["l2"]["last_error"]
    assert "AitoError" in last and "500" in last and "/data/cache_entries" in last
    # The detail is not lost: it goes to the operator's log.
    assert "SECRET-ROW-CONTENT" in log


def test_cache_status_does_not_serve_the_process_wide_last_error(monkeypatch):
    monkeypatch.setattr(cache, "_aito", BrokenAito())
    cache.set("k", {"v": 1})
    client = TestClient(app_module.app)

    status = client.get("/api/cache/status", params={"customer_id": "CUST-0000"}).json()

    assert status["l2"]["failed_writes"] == 1
    assert "last_error" not in status["l2"], "a per-customer endpoint shows a global value"


class ExistingTableAito(WorkingAito):
    """A second PUT of the same table is a 4xx, which is how init() finds it exists."""

    def _request(self, method, path, json=None, **kwargs):
        if method == "PUT":
            raise AitoError("table exists", status_code=400)
        return super()._request(method, path, json=json, **kwargs)


def test_an_unreachable_l2_at_startup_is_counted_but_an_existing_table_is_not(monkeypatch):
    # init() swallowed every AitoError as "table likely exists", so an L2 that
    # was down from the first moment looked healthy until traffic arrived.
    cache.init(BrokenAito())
    assert cache.l2_health()["failed_writes"] == 1

    monkeypatch.setattr(cache, "_l2_failures", {"writes": 0, "deletes": 0, "reads": 0})
    cache.init(ExistingTableAito())
    assert cache.l2_health()["failed_writes"] == 0, "an existing table is not a failure"
