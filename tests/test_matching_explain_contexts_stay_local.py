"""The explain contexts are not shared state, and a cold rebuild runs once.

An explain context is the whole open ledger as it stood when each payment
was ranked. Measured offline on the real shape, that is 27-43 KiB per
tenant against a 7 KiB pairs payload -- four to six times the page the
branch exists to slim. Writing it to the shared L2 table on every
cache.set would put those bytes on the shared instance for every tenant
the keep-warm pass visits. A lost context costs one rebuild, so it lives
in this process only.

When it is lost (TTL, restart, another instance), concurrent explain
requests would each rebuild the pairing; they share one rebuild instead.
(Adversary pass, 2026-10-31.)
"""

import os
import threading

os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")
os.environ.setdefault("CACHE_WATCH_SECONDS", "0")

import pytest                                              # noqa: E402

from src import app as app_module                           # noqa: E402
from src import cache_keys                                # noqa: E402
from src import cache                                       # noqa: E402

TENANT = "CUST-0000"
TXN = "CUST-0000-TXN-000001"


class RecordingAito:
    """Stands in for the shared instance; remembers what was written to it."""

    def __init__(self):
        self.written_keys = []

    def _request(self, method, path, json=None):
        if json and "key" in json:
            self.written_keys.append(json["key"])
        return {}

    def search(self, *args, **kwargs):
        return {"hits": []}


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    monkeypatch.setattr(cache, "_aito", RecordingAito())
    cache._l1.clear()
    monkeypatch.setattr(cache_keys, "V2_PREFIX", "v2:")
    yield
    cache._l1.clear()


def _result():
    return {"pairs": [], "metrics": {}, "explain_contexts": {TXN: {"txn": {}, "open_invoices": []}}}


def test_local_only_set_never_reaches_the_shared_table():
    cache.set("k", {"v": 1}, local_only=True)

    assert cache.get("k") == {"v": 1}
    assert cache._aito.written_keys == []


def test_the_pairs_go_to_the_shared_table_but_their_contexts_do_not(monkeypatch):
    monkeypatch.setattr(app_module, "match_all", lambda *a, **k: _result())

    app_module._match_and_cache(TENANT)

    assert cache._aito.written_keys == [f"matching:v2:{TENANT}"]
    assert cache.get(f"matching_ctx:v2:{TENANT}") == {TXN: {"txn": {}, "open_invoices": []}}


def test_concurrent_cold_explains_share_one_rebuild(monkeypatch):
    rebuilds = []
    release = threading.Event()

    def slow_match_all(*args, **kwargs):
        rebuilds.append(1)
        release.wait(timeout=5)
        return _result()

    monkeypatch.setattr(app_module, "match_all", slow_match_all)
    monkeypatch.setattr(app_module, "explain_match", lambda *a, **k: [])

    errors = []

    def ask():
        try:
            app_module.matching_explain(customer_id=TENANT, transaction_id=TXN,
                                        invoice_id="INV-1")
        except Exception as exc:                                   # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    # Let every thread reach the cold path before the rebuild finishes.
    threading.Event().wait(0.3)
    release.set()
    for t in threads:
        t.join(timeout=10)

    assert len(rebuilds) == 1, f"{len(rebuilds)} rebuilds for 4 concurrent cold explains"


def test_concurrent_cold_page_loads_share_one_pairing(monkeypatch):
    # /api/matching/pairs on a tenant with no precompute (a refused one, or a
    # lite tenant) cold-starts match_all per visitor. On the shared instance
    # that is N pairings of the same ledger at once.
    monkeypatch.setattr(app_module.precomputed, "load", lambda cid, name: None)
    runs = []
    release = threading.Event()

    def slow_match_all(*args, **kwargs):
        runs.append(1)
        release.wait(timeout=5)
        return _result()

    monkeypatch.setattr(app_module, "match_all", slow_match_all)
    results = []
    threads = [threading.Thread(
        target=lambda: results.append(app_module.matching_pairs(customer_id=TENANT)))
        for _ in range(4)]
    for t in threads:
        t.start()
    threading.Event().wait(0.3)
    release.set()
    for t in threads:
        t.join(timeout=10)

    assert len(runs) == 1, f"{len(runs)} pairings for 4 concurrent cold page loads"
    assert len(results) == 4


# ── The lock's failure and scope behaviour (CPO review of #72) ──────────

def _load_concurrently(tenants, match_all_impl, monkeypatch):
    monkeypatch.setattr(app_module.precomputed, "load", lambda cid, name: None)
    monkeypatch.setattr(app_module, "match_all", match_all_impl)
    outcomes = []

    def ask(tenant):
        try:
            outcomes.append(("ok", app_module.matching_pairs(customer_id=tenant)))
        except Exception as exc:                                   # noqa: BLE001
            outcomes.append(("error", exc))

    threads = [threading.Thread(target=ask, args=(t,)) for t in tenants]
    for t in threads:
        t.start()
    return threads, outcomes


def test_waiters_get_a_failed_pairing_at_once_instead_of_each_rerunning_it(monkeypatch):
    # When the pairing fails nothing is cached, so waiters used to re-run it one
    # after another: the k-th visitor waited k times for the same error.
    runs = []

    def failing(*args, **kwargs):
        runs.append(1)
        threading.Event().wait(0.3)
        raise RuntimeError("Aito unreachable")

    threads, outcomes = _load_concurrently([TENANT] * 4, failing, monkeypatch)
    for t in threads:
        t.join(timeout=10)

    assert len(runs) == 1, f"{len(runs)} failing pairings for 4 visitors"
    assert [kind for kind, _ in outcomes] == ["error"] * 4


def test_a_waiter_that_waited_too_long_computes_for_itself(monkeypatch):
    # No lock timeout would let waiters pile up behind a pairing that takes
    # minutes and exhaust the threadpool for every other tenant.
    monkeypatch.setattr(app_module, "PAIRING_WAIT_SECONDS", 0.2)
    runs = []
    release = threading.Event()

    def slow(*args, **kwargs):
        runs.append(1)
        release.wait(timeout=5)
        return _result()

    threads, outcomes = _load_concurrently([TENANT] * 2, slow, monkeypatch)
    threading.Event().wait(0.8)
    assert len(runs) == 2, "the second visitor is still queued behind the lock"
    release.set()
    for t in threads:
        t.join(timeout=10)


def test_the_lock_is_per_tenant_not_global(monkeypatch):
    # Both pairings must be inside match_all at the same moment; a global lock
    # would never let the second one start and the barrier would time out.
    barrier = threading.Barrier(2, timeout=3)

    def both_at_once(*args, **kwargs):
        barrier.wait()
        return _result()

    threads, outcomes = _load_concurrently(["CUST-0000", "CUST-0001"], both_at_once, monkeypatch)
    for t in threads:
        t.join(timeout=10)

    assert [kind for kind, _ in outcomes] == ["ok", "ok"], outcomes
