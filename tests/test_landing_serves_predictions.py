"""The home page payload carries a prediction per tenant, with its $why.

A precomputed payload in the old shape (the most common routing among 50
invoices, under "templates") must not be served as if it were current: the
page would show no tenant any answer. It is recomputed live until the
precompute step rewrites it.
"""

import pytest
from fastapi.testclient import TestClient

import src.app as app_module

VENDOR = "Kardex Finland Oy"
TENANTS = ["CUST-9103", "CUST-9104"]
VENDORS = [{"vendor": VENDOR, "tenant_count": 2, "distinct_gls": 2,
            "tenants": [{"customer_id": c} for c in TENANTS]}]


def routing_for(customer_id):
    answer = lambda value, p: {"value": value, "display": value, "p": p, "why": []}
    return {"vendor": VENDOR, "customer_id": customer_id, "gl_code": answer("4400", 0.8),
            "approver": answer("E1", 0.9), "cost_centre": answer("CC-100", 0.7)}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("src.multitenancy_service.compute_shared_vendors", lambda: VENDORS)
    monkeypatch.setattr("src.vendor_routing.predict_vendor_routing",
                        lambda _client, customer_id, vendor: routing_for(customer_id))
    return TestClient(app_module.app)


def test_a_precomputed_payload_is_served_as_it_is(client, monkeypatch):
    payload = {"vendors": VENDORS, "routing": {f"{VENDOR}|{c}": routing_for(c) for c in TENANTS}}
    monkeypatch.setattr(app_module.precompute_store, "get", lambda name: payload)

    body = client.get("/api/multitenancy/landing").json()

    assert set(body["routing"]) == {f"{VENDOR}|{c}" for c in TENANTS}
    assert "templates" not in body


def test_a_payload_in_the_old_template_shape_is_recomputed_live(client, monkeypatch):
    old = {"vendors": VENDORS, "templates": {f"{VENDOR}|{TENANTS[0]}": {"fields": {"gl_code": "4400"}}}}
    monkeypatch.setattr(app_module.precompute_store, "get", lambda name: old)

    body = client.get("/api/multitenancy/landing").json()

    assert body["routing"][f"{VENDOR}|{TENANTS[0]}"]["gl_code"]["p"] == 0.8
    assert "templates" not in body


def test_a_tenant_with_no_answer_is_left_out_not_invented(client, monkeypatch):
    monkeypatch.setattr(app_module.precompute_store, "get", lambda name: None)
    monkeypatch.setattr("src.vendor_routing.predict_vendor_routing",
                        lambda _client, customer_id, vendor: None if customer_id == TENANTS[1] else routing_for(customer_id))

    body = client.get("/api/multitenancy/landing").json()

    assert list(body["routing"]) == [f"{VENDOR}|{TENANTS[0]}"]
