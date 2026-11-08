"""In PUBLIC_DEMO mode nothing a visitor types is stored.

The public demo writes to a shared Aito instance that every visitor reads
from, so text a visitor types must not land there:
  - a Form Fill submit logs the outcome (field, accepted, confidence) but
    not predicted_value or user_value;
  - a help impression logs the article, page and click but not the query
    (the help ranking matches the query against article text, never against
    stored impressions, so nothing is lost);
  - a Form Fill prediction is not cached, because its cache key is the typed
    input and the cache's second layer is a shared Aito table.
Off (the default), all three behave as before.
"""

import time

import pytest
from fastapi.testclient import TestClient

import src.app as app_module
from src import cache, public_demo

TYPED = "Visitor Typed Vendor Oy"


class Store:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def _request(self, method, path, json=None, **kwargs):
        assert path == "/data/prediction_log/batch", path
        self.tables.setdefault("prediction_log", []).extend(json)
        return {}

    def insert_batch(self, table, rows):
        self.tables.setdefault(table, []).extend(rows)


def wait_for(store, table):
    deadline = time.monotonic() + 5
    while not store.tables.get(table) and time.monotonic() < deadline:
        time.sleep(0.01)
    return store.tables.get(table, [])


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(app_module, "v2_client", s)
    return s


@pytest.fixture(params=[True, False], ids=["public", "private"])
def mode(request, monkeypatch):
    monkeypatch.setattr(public_demo, "ENABLED", request.param)
    return request.param


def test_a_submit_stores_the_outcome_and_not_the_typed_values(store, mode):
    r = TestClient(app_module.app).post("/api/formfill/submit", json={
        "customer_id": "CUST-0000",
        "fields": [{"field": "vendor", "predicted_value": "Kesko Oyj", "user_value": TYPED,
                    "source": "user", "confidence": 0.4, "accepted": False}],
    })
    assert r.json() == {"logged": 1}, r.text
    [row] = wait_for(store, "prediction_log")
    assert (row["field"], row["accepted"], row["confidence"]) == ("vendor", False, 0.4)
    if mode:
        assert row["predicted_value"] is None and row["user_value"] is None, row
    else:
        assert (row["predicted_value"], row["user_value"]) == ("Kesko Oyj", TYPED)


def test_a_help_impression_stores_no_query(store, mode):
    r = TestClient(app_module.app).post("/api/help/impression", json={
        "article_id": "ART-1", "customer_id": "CUST-0000", "page": "/invoices",
        "query": TYPED, "clicked": True,
    })
    assert r.json() == {"ok": True}
    [row] = wait_for(store, "help_impressions")
    assert (row["article_id"], row["clicked"]) == ("ART-1", True)
    assert row["query"] == ("" if mode else TYPED)


def test_a_formfill_prediction_is_not_cached_by_its_typed_input(store, mode, monkeypatch):
    calls, cached = [], {}
    monkeypatch.setattr(app_module, "predict_fields", lambda client, where: calls.append(where) or {"n": len(calls)})
    monkeypatch.setattr(cache, "get", lambda key: cached.get(key))
    monkeypatch.setattr(cache, "set", lambda key, value, ttl=None: cached.__setitem__(key, value))
    client = TestClient(app_module.app)
    for _ in range(2):
        r = client.post("/api/formfill/predict", json={"customer_id": "CUST-0000", "vendor": TYPED})
        assert r.status_code == 200, r.text
    assert len(calls) == (2 if mode else 1)
    assert (TYPED in str(list(cached))) is (not mode)
