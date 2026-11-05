"""The app is actually wired to the customer roster.

tests/test_customer_roster.py covers the loader. These cover the two places
that use it, which could otherwise be switched off or hard-coded with every
other test still green: the middleware that rejects an unknown customer_id,
and the health report that says whether the roster is there.
"""

import pytest
from fastapi.testclient import TestClient

import src.app as app_module

client = TestClient(app_module.app)

# A route that answers without touching Aito, so only the middleware decides.
PATH = "/api/quality/domains"


@pytest.fixture
def roster(monkeypatch):
    def set_roster(ids: set[str]):
        monkeypatch.setattr(app_module, "_load_known_customers", lambda: ids)
    return set_roster


def test_an_unknown_customer_id_is_a_400_when_the_roster_is_loaded(roster):
    roster({"CUST-0000"})

    response = client.get(PATH, params={"customer_id": "CUST-NOPE"})

    assert response.status_code == 400
    assert "unknown customer_id" in response.json()["error"]


def test_a_known_customer_id_passes_the_middleware(roster):
    roster({"CUST-0000"})

    assert client.get(PATH, params={"customer_id": "CUST-0000"}).status_code == 200


def test_an_empty_customer_id_is_a_400_whatever_the_roster(roster):
    roster(set())

    assert client.get(PATH, params={"customer_id": ""}).status_code == 400


@pytest.mark.parametrize("ids,status", [({"CUST-0000"}, "ok"), (set(), "degraded")])
def test_api_health_reports_whether_the_roster_is_there(roster, monkeypatch, ids, status):
    roster(ids)
    monkeypatch.setattr(app_module.cache, "get", lambda key: None)
    monkeypatch.setattr(app_module.cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(app_module.aito, "check_connectivity", lambda: True)

    body = client.get("/api/health").json()

    assert body["status"] == status
    assert body["roster_count"] == len(ids)


@pytest.mark.parametrize("ids", [{"CUST-0000", "CUST-0001"}, set()])
def test_healthz_carries_the_roster_size(roster, ids):
    roster(ids)

    assert client.get("/healthz").json() == {"ok": True, "roster_count": len(ids)}
