"""The precompute store's v1/v2 namespacing.

A precompute output is only valid for the API generation that produced
it. Both generations write to the same `precompute_entries` table and
the same `data/precomputed/` tree, so the only thing keeping them apart
is the key namespace — which makes it worth pinning.

The failure this guards against is quiet: a v2 deployment reading a
v1-derived projection gets a perfectly well-formed payload with numbers
no v2 query would produce. Nothing raises.
"""

import importlib

import pytest

from src import precompute_store


def reload_store(monkeypatch, v2_env: str | None):
    """Re-import the store with AITO_V2_ENV set or unset.

    The namespace is read at import time (it has to be — it decides
    where `./do precompute` writes before any client exists), so a test
    that changes it has to reload the module.
    """
    if v2_env is None:
        monkeypatch.delenv("AITO_V2_ENV", raising=False)
    else:
        monkeypatch.setenv("AITO_V2_ENV", v2_env)
    return importlib.reload(precompute_store)


@pytest.fixture(autouse=True)
def restore_module_after_each_test():
    """Leave the module as the rest of the suite expects to find it."""
    yield
    importlib.reload(precompute_store)


class TestNamespace:
    def test_v1_uses_the_unprefixed_namespace(self, monkeypatch):
        store = reload_store(monkeypatch, None)
        assert store.namespace() == ""

    def test_setting_the_v2_env_switches_the_namespace(self, monkeypatch):
        store = reload_store(monkeypatch, "v2-demo")
        assert store.namespace() == "v2:"

    def test_a_blank_v2_env_is_not_a_v2_run(self, monkeypatch):
        # `AITO_V2_ENV=` in a shell profile shouldn't silently switch
        # the whole store over — app.py strips the same way.
        store = reload_store(monkeypatch, "   ")
        assert store.namespace() == ""


class TestBootstrapPaths:
    """Where the on-disk fallback JSON lives, per namespace."""

    def test_v1_per_customer_path_is_unchanged(self, monkeypatch):
        store = reload_store(monkeypatch, None)
        path = store.bootstrap_path(store.per_customer_key("CUST-0000", "invoices_pending"))
        assert path.parts[-3:] == ("precomputed", "CUST-0000", "invoices_pending.json")

    def test_v1_flat_key_path_is_unchanged(self, monkeypatch):
        store = reload_store(monkeypatch, None)
        assert store.bootstrap_path("landing").parts[-2:] == ("precomputed", "landing.json")

    def test_v2_output_lands_in_its_own_subtree(self, monkeypatch):
        store = reload_store(monkeypatch, "v2-demo")
        path = store.bootstrap_path(store.per_customer_key("CUST-0000", "invoices_pending"))
        # `v2/` between the root and the customer: a v2 precompute run
        # must never overwrite the v1 bootstrap files kept in git.
        assert path.parts[-4:] == ("precomputed", "v2", "CUST-0000", "invoices_pending.json")

    def test_v2_flat_key_lands_in_its_own_subtree(self, monkeypatch):
        store = reload_store(monkeypatch, "v2-demo")
        assert store.bootstrap_path("landing").parts[-3:] == ("precomputed", "v2", "landing.json")


class TestReadWriteIsolation:
    """The point of the namespace: one generation cannot read the other's.

    These pin the L1 layer, so they point the on-disk fallback at an
    empty directory. Otherwise a real `./do precompute` run on the
    developer's machine supplies the very file a miss is asserting on,
    and the test passes or fails depending on local state.
    """

    @pytest.fixture(autouse=True)
    def isolate_the_bootstrap_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(precompute_store, "_FALLBACK_DIR", tmp_path)

    def test_a_v1_write_is_invisible_to_a_v2_read(self, monkeypatch, tmp_path):
        v1 = reload_store(monkeypatch, None)
        monkeypatch.setattr(v1, "_FALLBACK_DIR", tmp_path)
        v1._l1["cust:CUST-0000:quality_overview"] = {"automation_pct": 82}
        assert v1.get(v1.per_customer_key("CUST-0000", "quality_overview")) == {"automation_pct": 82}

        # Same key, v2 process. Without a namespace this would return
        # the v1 number and render it as a v2 measurement.
        v2 = reload_store(monkeypatch, "v2-demo")
        monkeypatch.setattr(v2, "_FALLBACK_DIR", tmp_path)
        v2._l1["cust:CUST-0000:quality_overview"] = {"automation_pct": 82}
        assert v2.get(v2.per_customer_key("CUST-0000", "quality_overview")) is None

    def test_a_v2_write_is_read_back_under_the_v2_namespace(self, monkeypatch, tmp_path):
        store = reload_store(monkeypatch, "v2-demo")
        monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
        store._l1["v2:cust:CUST-0000:quality_overview"] = {"automation_pct": 79}
        assert store.get(store.per_customer_key("CUST-0000", "quality_overview")) == {
            "automation_pct": 79
        }

    def test_invalidate_targets_the_active_namespace(self, monkeypatch, tmp_path):
        store = reload_store(monkeypatch, "v2-demo")
        monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
        store._l1["v2:landing"] = {"vendors": []}
        store._l1["landing"] = {"vendors": ["v1 value"]}

        store.invalidate("landing")

        assert "v2:landing" not in store._l1
        assert store._l1["landing"] == {"vendors": ["v1 value"]}, \
            "invalidating on v2 must not evict the v1 entry"
