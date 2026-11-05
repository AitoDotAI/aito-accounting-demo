"""The one place a cache key is spelled.

Every cached answer is keyed `<name>:<prefix><suffix>`, where the prefix
(`v2:` when the demo runs against an Aito v2 environment, empty otherwise)
keeps v1 and v2 results in separate slots so flipping AITO_V2_ENV can never
serve a v1 answer for a v2 query out of a warm cache.

It is a separate module so that code which only needs a key (the nav
badges, rule governance's cache drops) does not have to import the app,
which builds clients and starts the cache watcher on import. The key
spelling tests (tests/test_page_cache_keys_have_one_spelling.py) require
every `cache.get/set/delete` argument to come from here.
"""

import os

from src.aito_v2_client import resolve_env

V2_PREFIX = "v2:" if resolve_env(os.environ.get("AITO_V2_ENV", "").strip())[0] else ""


def scoped_key(name: str, suffix: str, prefix: str | None = None) -> str:
    """`<name>:<prefix><suffix>`; `prefix` overrides the running generation's.

    The override exists for the code that must drop an entry written by
    either generation (rule governance after a promotion).
    """
    return f"{name}:{V2_PREFIX if prefix is None else prefix}{suffix}"


def page_cache_key(name: str, customer_id: str, prefix: str | None = None) -> str:
    """The L1/L2 cache key for one page's payload for one tenant."""
    return scoped_key(name, customer_id, prefix)


def derived_key(name: str, customer_id: str, *parts: object) -> str:
    """A tenant's key narrowed by further parts: `name:<prefix><tenant>:a:b`."""
    return scoped_key(name, ":".join([customer_id, *map(str, parts)]))
