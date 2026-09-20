"""Administrative cache invalidation: who may call it, and what it drops.

These import `src.admin_ops`, never `src.app`. Importing the app
constructs live Aito clients and PUTs schemas at module level, which
stops the suite being hermetic — it once made an unrelated formfill test
assert 4 == 6 by disturbing its httpx mocking. See ADR 0022.
"""

import pytest

from src import admin_ops, cache, precompute_store


@pytest.fixture(autouse=True)
def isolated_caches(monkeypatch):
    """L1-only, and empty. `_aito` is what makes these stores reach L2."""
    monkeypatch.setattr(cache, "_aito", None)
    monkeypatch.setattr(precompute_store, "_aito", None)
    cache.drop_local()
    precompute_store.invalidate()
    yield
    cache.drop_local()
    precompute_store.invalidate()


class TestWhoMayCall:
    def test_disabled_when_no_token_is_configured(self, monkeypatch):
        """A clean checkout must expose no administrative surface."""
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)

        with pytest.raises(admin_ops.AdminDisabled):
            admin_ops.check_admin_token("anything")

    def test_missing_token_is_forbidden(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "s3cret")

        with pytest.raises(admin_ops.AdminForbidden):
            admin_ops.check_admin_token(None)

    def test_wrong_token_is_forbidden(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "s3cret")

        with pytest.raises(admin_ops.AdminForbidden):
            admin_ops.check_admin_token("guess")

    def test_correct_token_is_accepted(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "s3cret")

        admin_ops.check_admin_token("s3cret")  # does not raise

    def test_a_prefix_of_the_token_is_not_enough(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "s3cret")

        with pytest.raises(admin_ops.AdminForbidden):
            admin_ops.check_admin_token("s3c")


class TestWhatItDrops:
    def test_drops_both_in_process_caches(self):
        cache.set("some-key", {"v": 1})
        precompute_store._l1["v2:cust:CUST-0000:matching_pairs"] = {"pairs": []}

        admin_ops.drop_in_process_caches()

        assert cache.get("some-key") is None
        assert precompute_store._l1 == {}

    def test_reports_how_many_it_dropped(self):
        cache.set("a", 1)
        cache.set("b", 2)
        precompute_store._l1["x"] = 1

        result = admin_ops.drop_in_process_caches()

        assert result == {"cache_entries_dropped": 2,
                          "precompute_entries_dropped": 1}

    def test_does_not_delete_the_shared_aito_cache_table(self, monkeypatch):
        """`cache.clear()` DROPs and recreates `cache_entries`, which other
        processes read. Reloading one container must not do that."""
        calls = []
        monkeypatch.setattr(cache, "clear", lambda: calls.append("clear"))

        admin_ops.drop_in_process_caches()

        assert calls == []
