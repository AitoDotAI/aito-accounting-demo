"""/api/cache/status reads the keys the app writes (CPO review, 2026-10-31).

The five "warm" flags read `cache.get(f"invoices:{customer_id}")` while
every writer in the app uses `f"invoices:{_V2}{customer_id}"`. `_V2` is
"v2:" whenever the demo runs against a v2 environment -- which is how it
is deployed -- so a fully warm cache reported stone cold on all five
surfaces, and anybody using the endpoint to decide whether a tenant is
demo-ready got the wrong answer.

The fix is not five prefixes: it is one key builder, so a reader and a
writer cannot disagree again. That is what these tests pin.
"""

import os

os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")
os.environ.setdefault("CACHE_WATCH_SECONDS", "0")

import pytest                                              # noqa: E402

from src import app as app_module                           # noqa: E402

TENANT = "CUST-0000"
SURFACES = [
    ("invoices_warm", "invoices"),
    ("quality_warm", "quality"),
    ("matching_warm", "matching"),
    ("rules_warm", "rules"),
    ("anomalies_warm", "anomalies"),
]


@pytest.fixture(autouse=True)
def _nothing_precomputed(monkeypatch):
    monkeypatch.setattr("src.precompute_store.get", lambda key: None)
    monkeypatch.setattr(app_module.precomputed, "has", lambda cid, name: False)
    # The suite runs with AITO_V2_ENV unset, so _V2 is "" at import and a
    # key built without the prefix is indistinguishable from one built
    # with it. The bug only exists in v2 mode, so the tests have to be in
    # v2 mode. The builder reads the module global at call time.
    monkeypatch.setattr(app_module, "_V2", "v2:")


@pytest.mark.parametrize("flag,prefix", SURFACES)
def test_a_warm_cache_reports_warm(monkeypatch, flag, prefix):
    """Keyed as the app's writers key it, spelled out rather than built.

    Deliberately NOT `page_cache_key(...)`: an expectation computed by
    the code under test agrees with it however wrong it is. The first
    version of this test did exactly that and passed with the prefix
    removed from the builder.
    """
    written = f"{prefix}:v2:{TENANT}"
    monkeypatch.setattr(app_module.cache, "get",
                        lambda key: {"warm": True} if key == written else None)
    assert app_module.cache_status(customer_id=TENANT)[flag] is True, \
        f"{flag} read a different key than {written}"


@pytest.mark.parametrize("flag,prefix", SURFACES)
def test_a_cold_cache_reports_cold(monkeypatch, flag, prefix):
    monkeypatch.setattr(app_module.cache, "get", lambda key: None)
    assert app_module.cache_status(customer_id=TENANT)[flag] is False


def test_the_key_builder_carries_the_environment_prefix():
    # The whole bug in one line: in v2 mode the key is prefixed, and a
    # reader that spells it by hand loses the prefix. Compared against a
    # literal, not against _V2 -- the autouse fixture has set it.
    assert app_module.page_cache_key("invoices", TENANT) == f"invoices:v2:{TENANT}"


def test_every_writer_in_the_app_uses_the_builder():
    """No hand-spelled page cache key is left to drift out of step."""
    import pathlib
    import re
    source = pathlib.Path(app_module.__file__).read_text()
    stray = re.findall(
        r'f"(?:invoices|quality|matching|rules|anomalies):\{[^"]*\}"', source)
    assert stray == [], f"hand-spelled page cache keys remain: {stray}"
