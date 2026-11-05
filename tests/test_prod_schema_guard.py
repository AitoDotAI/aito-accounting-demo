"""Tooling must not change the schema of the production demo database.

On 2026-09-20 a v1 schema PUT from a loader run reached the production
database (`shared.aito.ai/db/aito-accounting-demo`). Prod was intact, but
nothing stopped the next one. These tests pin the guard: a schema PUT or
DELETE against prod is refused before any request leaves the process,
unless the operator names the database twice (flag + confirmation).
"""

import pytest

from src.aito_client import AitoClient
from src.aito_v2_client import AitoV2Client
from src.config import Config
from src.schema_write_guard import ProdSchemaWriteRefused

PROD_URL = "https://shared.aito.ai/db/aito-accounting-demo"
LOCAL_URL = "http://localhost:8080"
SCHEMA = {"type": "table", "columns": {"id": {"type": "String"}}}


@pytest.fixture(autouse=True)
def no_override(monkeypatch):
    monkeypatch.delenv("AITO_ALLOW_PROD_SCHEMA_WRITE", raising=False)
    monkeypatch.delenv("AITO_PROD_SCHEMA_CONFIRM", raising=False)


def v1(url: str) -> AitoClient:
    return AitoClient(Config(aito_api_url=url, aito_api_key="k"))


def test_plain_v1_schema_put_to_prod_is_refused_before_any_request(httpx_mock):
    with pytest.raises(ProdSchemaWriteRefused, match="aito-accounting-demo"):
        v1(PROD_URL)._request("PUT", "/schema/invoices", json=SCHEMA)
    assert httpx_mock.get_requests() == []


def test_plain_v1_schema_delete_on_prod_is_refused(httpx_mock):
    with pytest.raises(ProdSchemaWriteRefused):
        v1(PROD_URL)._request("DELETE", "/schema/invoices")
    assert httpx_mock.get_requests() == []


def test_trailing_slash_and_case_do_not_dodge_the_guard(httpx_mock):
    with pytest.raises(ProdSchemaWriteRefused):
        v1(PROD_URL.upper() + "/")._request("PUT", "/schema/invoices", json=SCHEMA)


def test_v2_master_schema_write_to_prod_is_refused(httpx_mock):
    client = AitoV2Client(PROD_URL, "k", env="master")
    with pytest.raises(ProdSchemaWriteRefused):
        client.create_collection("invoices", SCHEMA["columns"])
    with pytest.raises(ProdSchemaWriteRefused):
        AitoV2Client(PROD_URL, "k").delete_collection("invoices")
    assert httpx_mock.get_requests() == []


def test_a_branch_environment_of_prod_may_be_written(httpx_mock):
    httpx_mock.add_response(json={})
    AitoV2Client(PROD_URL, "k", env="scratch").create_collection("t", SCHEMA["columns"])
    assert len(httpx_mock.get_requests()) == 1


def test_local_engine_schema_write_is_untouched(httpx_mock):
    httpx_mock.add_response(json={})
    v1(LOCAL_URL)._request("PUT", "/schema/invoices", json=SCHEMA)
    assert len(httpx_mock.get_requests()) == 1


def test_reads_and_data_writes_to_prod_are_untouched(httpx_mock):
    httpx_mock.add_response(json={}, is_reusable=True)
    client = v1(PROD_URL)
    client._request("GET", "/schema")
    client._request("POST", "/data/invoices/batch", json=[])
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize("table", ["cache_entries", "cache_versions", "precompute_entries"])
def test_the_apps_own_bookkeeping_tables_are_still_created_on_startup(httpx_mock, table):
    httpx_mock.add_response(json={})
    v1(PROD_URL)._request("PUT", f"/schema/{table}", json=SCHEMA)
    assert len(httpx_mock.get_requests()) == 1


def test_flag_alone_is_not_enough(httpx_mock, monkeypatch):
    monkeypatch.setenv("AITO_ALLOW_PROD_SCHEMA_WRITE", "1")
    with pytest.raises(ProdSchemaWriteRefused):
        v1(PROD_URL)._request("PUT", "/schema/invoices", json=SCHEMA)


def test_flag_with_wrong_confirmation_is_not_enough(httpx_mock, monkeypatch):
    monkeypatch.setenv("AITO_ALLOW_PROD_SCHEMA_WRITE", "1")
    monkeypatch.setenv("AITO_PROD_SCHEMA_CONFIRM", "yes")
    with pytest.raises(ProdSchemaWriteRefused):
        v1(PROD_URL)._request("PUT", "/schema/invoices", json=SCHEMA)


def test_flag_plus_named_confirmation_lets_the_write_through(httpx_mock, monkeypatch):
    httpx_mock.add_response(json={})
    monkeypatch.setenv("AITO_ALLOW_PROD_SCHEMA_WRITE", "1")
    monkeypatch.setenv("AITO_PROD_SCHEMA_CONFIRM", "aito-accounting-demo")
    v1(PROD_URL)._request("PUT", "/schema/invoices", json=SCHEMA)
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize(
    "base_url",
    [
        "https://shared.aito.ai:443/db/aito-accounting-demo",
        "HTTPS://Shared.Aito.AI/DB/Aito-Accounting-Demo/",
        "https://shared.aito.ai//db//aito-accounting-demo",
        "https://shared.aito.ai/db/aito-accounting-demo/api/v1",
        "https://shared.aito.ai/db/aito-accounting-demo/api/v2/",
        "http://shared.aito.ai/db/aito-accounting-demo",
    ],
)
def test_every_spelling_of_the_prod_base_url_is_guarded(httpx_mock, base_url):
    with pytest.raises(ProdSchemaWriteRefused):
        v1(base_url)._request("PUT", "/schema/invoices", json=SCHEMA)
    with pytest.raises(ProdSchemaWriteRefused):
        AitoV2Client(base_url, "k").delete_collection("invoices")
    assert httpx_mock.get_requests() == []


def test_a_look_alike_database_on_the_same_host_is_not_prod(httpx_mock):
    httpx_mock.add_response(json={})
    v1("https://shared.aito.ai/db/aito-accounting-demo-copy")._request(
        "PUT", "/schema/invoices", json=SCHEMA
    )
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/schema/invoices",
        "/api/v2/schema/invoices",
        "//schema/invoices",
        "/schema//invoices",
        "/schema/cache_entries/../invoices",
        "/schema/cache_entries/extra",
        "/schema/cache_entries%2F..%2Finvoices",
    ],
)
def test_a_schema_path_in_any_spelling_is_guarded(httpx_mock, path):
    with pytest.raises(ProdSchemaWriteRefused):
        v1(PROD_URL)._request("DELETE", path)
    assert httpx_mock.get_requests() == []


def test_the_clients_pass_relative_paths_only():
    """The guard sees what `_request` is given; callers must not pass full URLs."""
    import pathlib
    import re

    calls = []
    for source in pathlib.Path("src").glob("*.py"):
        calls += re.findall(r'_request\(\s*"[A-Z]+",\s*f?"([^"]*)"', source.read_text())
    assert calls
    assert all(path.startswith("/") and "/api/" not in path for path in calls), calls
