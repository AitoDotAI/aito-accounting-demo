"""Refuse schema changes to the production demo database from tooling.

A schema PUT replaces a table and a DELETE drops it with its data. On
2026-09-20 a loader run aimed at localhost reached `shared.aito.ai` and
wrote a v1 schema there. Both clients call `refuse_prod_schema_write`
before sending, so the refusal happens in-process, not at Aito.

Override, for the rare deliberate change: set BOTH
`AITO_ALLOW_PROD_SCHEMA_WRITE=1` and `AITO_PROD_SCHEMA_CONFIRM=aito-accounting-demo`.
"""

import os
import posixpath
import re
from urllib.parse import unquote, urlsplit

PROD_HOST = "shared.aito.ai"
PROD_DB_NAME = "aito-accounting-demo"
PROD_DEMO_DB = f"{PROD_HOST}/db/{PROD_DB_NAME}"

# The app creates these on every startup and `cache.clear()` recreates one.
# They hold cache and precompute rows, not demo data.
APP_OWNED_TABLES = frozenset({"cache_entries", "cache_versions", "precompute_entries"})

# A v2 branch environment is a scratch copy; only master is production.
_MASTER_ENVS = {None, "", "master", "env.master"}


class ProdSchemaWriteRefused(RuntimeError):
    """A schema PUT/DELETE aimed at the production demo database."""


def _clean_path(path: str) -> str:
    """Collapse `//`, `..` and percent-escapes so one table has one spelling."""
    return posixpath.normpath("/" + unquote(path).lstrip("/"))


def _is_prod(base_url: str, env: str | None) -> bool:
    """Compare host and database path, whatever way the base URL is spelled.

    Port, scheme, case, repeated slashes and a trailing `/api/v1|v2` all
    still name prod. `/env/<name>` in the URL is a branch, not prod.
    """
    parts = urlsplit(base_url if "//" in base_url else f"//{base_url}")
    path = _clean_path(parts.path.lower())
    path = re.sub(r"/api/v[12]$", "", path)
    return (
        (parts.hostname or "").lower() == PROD_HOST
        and path == f"/db/{PROD_DB_NAME}"
        and env in _MASTER_ENVS
    )


def refuse_prod_schema_write(
    base_url: str, method: str, path: str, env: str | None = None
) -> None:
    """Raise ProdSchemaWriteRefused for a schema PUT/DELETE on prod."""
    path = re.sub(r"^/api/v[12](?=/)", "", _clean_path(path))
    if method.upper() not in ("PUT", "DELETE") or not path.startswith("/schema"):
        return
    if not _is_prod(base_url, env):
        return
    if path.removeprefix("/schema/") in APP_OWNED_TABLES:
        return
    if (
        os.environ.get("AITO_ALLOW_PROD_SCHEMA_WRITE") == "1"
        and os.environ.get("AITO_PROD_SCHEMA_CONFIRM") == PROD_DB_NAME
    ):
        return
    raise ProdSchemaWriteRefused(
        f"Refusing {method} {path} on the production demo database "
        f"({PROD_DEMO_DB}): a schema write replaces or drops a table. "
        f"Point AITO_API_URL at a local engine or a v2 branch environment. "
        f"For a deliberate change set AITO_ALLOW_PROD_SCHEMA_WRITE=1 and "
        f"AITO_PROD_SCHEMA_CONFIRM={PROD_DB_NAME}."
    )
