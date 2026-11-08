"""One visitor's Form Fill text must never reach another visitor.

/api/formfill/submit logs each field to prediction_log, and /api/quality/audit
is a public GET over that log. Every visitor of the demo shares the same
tenants, so whatever visitor A typed (a vendor, a description, a value they
corrected) was listed for visitor B. Everything in a logged row except the
counts came from the visitor's request body, so the audit lists logged rows
with their outcome and confidence but without their values, and only names a
field the Form Fill actually has.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import src.app as app_module
from src import cache

SECRET_VENDOR = "Visitor A Private Vendor Oy"
SECRET_FIELD = "my_home_address"


class LogStore:
    """prediction_log as a list: batch writes append, searches filter by customer."""

    def __init__(self):
        self.rows = []

    def _request(self, method, path, json=None, **kwargs):
        if path == "/data/prediction_log/batch":
            self.rows.extend(json)
            return {}
        raise AssertionError(f"unexpected request {method} {path}")

    def search(self, table, where, limit=10, **kwargs):
        assert table == "prediction_log", table
        return {"hits": [r for r in self.rows if r["customer_id"] == where["customer_id"]][:limit]}


@pytest.fixture
def store(monkeypatch):
    s = LogStore()
    monkeypatch.setattr(app_module, "v2_client", s)
    cache._l1.clear()
    monkeypatch.setattr(cache, "get", lambda key: None)
    monkeypatch.setattr(cache, "set", lambda key, value, ttl=None: None)
    yield s
    cache._l1.clear()


def submit(client, store, fields):
    """Post a submit and wait for its background log write to land."""
    before = len(store.rows)
    r = client.post("/api/formfill/submit", json={"customer_id": "CUST-0000", "fields": fields})
    deadline = time.monotonic() + 5
    while r.status_code == 200 and len(store.rows) == before and time.monotonic() < deadline:
        time.sleep(0.01)
    return r


def test_visitor_b_does_not_see_what_visitor_a_typed(store):
    visitor_a, visitor_b = TestClient(app_module.app), TestClient(app_module.app)
    r = submit(visitor_a, store, [
        {"field": "vendor", "predicted_value": "Kesko Oyj", "user_value": SECRET_VENDOR,
         "source": "user", "confidence": 0.4, "accepted": False},
        {"field": "gl_code", "predicted_value": "4400", "user_value": "4400",
         "source": "predicted", "confidence": 0.9, "accepted": True},
    ])
    assert r.status_code == 200 and r.json() == {"logged": 2}, r.text

    audit = visitor_b.get("/api/quality/audit", params={"customer_id": "CUST-0000"}).json()

    assert SECRET_VENDOR not in json.dumps(audit)
    rows = {r["field"]: r for r in audit["rows"]}
    assert set(rows) == {"vendor", "gl_code"}
    for r in rows.values():
        assert r["predicted_value"] is None and r["user_value"] is None, r
        assert r["values_withheld"] is True, r
    # the outcome counts are what the audit is for, and they are unchanged
    assert audit["totals"] == {"total": 2, "accepted": 1, "overridden": 1, "accept_rate": 0.5}


def test_a_field_the_form_does_not_have_is_refused_at_submit(store):
    r = submit(TestClient(app_module.app), store, [
        {"field": SECRET_FIELD, "predicted_value": None, "user_value": "x",
         "source": "user", "confidence": 0, "accepted": False},
    ])
    assert r.status_code == 400, r.text
    assert SECRET_FIELD in r.json()["detail"]
    assert store.rows == []


def test_a_stored_row_with_an_unknown_field_is_listed_without_its_name(store):
    store.rows.append({"log_id": "LOG-old", "customer_id": "CUST-0000", "field": SECRET_FIELD,
                       "predicted_value": None, "user_value": "x", "source": "user",
                       "confidence": 0.0, "accepted": False, "timestamp": 1})
    audit = TestClient(app_module.app).get("/api/quality/audit", params={"customer_id": "CUST-0000"}).json()
    assert SECRET_FIELD not in json.dumps(audit)
    assert audit["rows"][0]["field"] == "(not a form field)"
