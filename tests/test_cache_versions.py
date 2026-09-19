"""Per-scope cache versions and the poll that acts on them.

These import the modules directly, never `src.app` — importing the app
constructs live Aito clients and PUTs schemas at module level, which
stops the suite being hermetic. See ADR 0022.
"""

import pytest

from src import admin_ops, cache, cache_versions, cache_watch, precompute_store


class FakeAito:
    """Records writes and replays a scripted versions table."""

    def __init__(self, rows=None, fail=False):
        self.rows = list(rows or [])
        self.fail = fail
        self.writes = []
        self.deletes = []

    def search(self, table, where, limit=1000):
        if self.fail:
            from src.aito_client import AitoError
            raise AitoError("unreachable")
        return {"hits": self.rows}

    def _request(self, method, path, json=None, timeout=120.0):
        if path == "/data/_delete":
            self.deletes.append(json)
        elif path.startswith("/data/"):
            self.writes.append(json)
        return {}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(cache, "_aito", None)
    monkeypatch.setattr(precompute_store, "_aito", None)
    cache.drop_local()
    precompute_store.invalidate()
    yield
    cache.drop_local()
    precompute_store.invalidate()
    cache_watch.stop()


class TestChangedSince:
    def test_a_moved_version_is_reported(self):
        changed = cache_versions.changed_since(
            {"precompute:matching_pairs": 100}, {"precompute:matching_pairs": 200})

        assert changed == {"precompute:matching_pairs"}

    def test_an_unchanged_version_is_not(self):
        assert cache_versions.changed_since({"a": 100}, {"a": 100}) == set()

    def test_a_new_scope_counts_as_changed(self):
        assert cache_versions.changed_since({}, {"table:invoices": 5}) == {"table:invoices"}

    def test_a_scope_missing_from_the_read_is_not_a_change(self):
        """An empty or partial read means Aito was unreachable. Treating
        absence as a change would drop every cache on every failed poll."""
        assert cache_versions.changed_since({"a": 100, "b": 200}, {"a": 100}) == set()


class TestScopedInvalidation:
    def _seed(self):
        precompute_store._l1.update({
            "v2:cust:CUST-0000:matching_pairs": 1,
            "v2:cust:CUST-0001:matching_pairs": 1,
            "v2:cust:CUST-0000:rules_candidates": 1,
        })

    def test_a_rebuilt_view_drops_only_that_view(self):
        """Rebuilding one view must not make the other tenants recompute a
        page that did not change."""
        self._seed()

        admin_ops.apply_version_changes({"precompute:matching_pairs"})

        assert set(precompute_store._l1) == {"v2:cust:CUST-0000:rules_candidates"}

    def test_a_rebuilt_view_drops_it_for_every_customer(self):
        self._seed()

        result = admin_ops.apply_version_changes({"precompute:matching_pairs"})

        assert result["precompute_entries_dropped"] == 2

    def test_a_changed_table_drops_everything(self):
        """Every derived view depends on the tables."""
        self._seed()

        admin_ops.apply_version_changes({"table:invoices"})

        assert precompute_store._l1 == {}

    def test_nothing_changed_drops_nothing(self):
        self._seed()

        result = admin_ops.apply_version_changes(set())

        assert result["precompute_entries_dropped"] == 0
        assert len(precompute_store._l1) == 3


class TestPolling:
    def test_a_moved_version_invalidates_and_updates_the_snapshot(self, monkeypatch):
        monkeypatch.setattr(cache_versions, "_aito",
                            FakeAito([{"scope": "precompute:matching_pairs", "version": 200}]))
        precompute_store._l1["v2:cust:CUST-0000:matching_pairs"] = 1

        snapshot, changed = cache_watch.poll_once({"precompute:matching_pairs": 100})

        assert changed == {"precompute:matching_pairs"}
        assert snapshot["precompute:matching_pairs"] == 200
        assert precompute_store._l1 == {}

    def test_an_unreachable_aito_changes_nothing(self, monkeypatch):
        """A transient outage must not become a recompute storm."""
        monkeypatch.setattr(cache_versions, "_aito", FakeAito(fail=True))
        precompute_store._l1["v2:cust:CUST-0000:matching_pairs"] = 1
        before = {"precompute:matching_pairs": 100}

        snapshot, changed = cache_watch.poll_once(before)

        assert changed == set()
        assert snapshot == before
        assert precompute_store._l1 == {"v2:cust:CUST-0000:matching_pairs": 1}


class TestWatcherLifecycle:
    def test_zero_interval_disables_the_watcher(self, monkeypatch):
        monkeypatch.setenv("CACHE_WATCH_SECONDS", "0")

        assert cache_watch.start() is False

    def test_a_non_integer_interval_disables_rather_than_crashing(self, monkeypatch):
        monkeypatch.setenv("CACHE_WATCH_SECONDS", "sixty")

        assert cache_watch.interval_seconds() == 0

    def test_it_does_not_start_twice(self, monkeypatch):
        monkeypatch.setenv("CACHE_WATCH_SECONDS", "60")
        monkeypatch.setattr(cache_versions, "_aito", FakeAito([]))

        assert cache_watch.start() is True
        assert cache_watch.start() is False


class TestBump:
    def test_bump_upserts_each_scope(self, monkeypatch):
        fake = FakeAito()
        monkeypatch.setattr(cache_versions, "_aito", fake)

        cache_versions.bump(["precompute:matching_pairs", "table:invoices"], now=1700)

        assert fake.writes == [
            {"scope": "precompute:matching_pairs", "version": 1700},
            {"scope": "table:invoices", "version": 1700},
        ]
        assert len(fake.deletes) == 2

    def test_bump_without_a_client_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(cache_versions, "_aito", None)

        cache_versions.bump(["table:invoices"])  # does not raise
