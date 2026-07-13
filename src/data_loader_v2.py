"""Build the dataset as Aito **v2 collections** in a branched environment.

The v2 counterpart of `data_loader.py`. It reuses the same table schemas
and the same fixtures, but:

- targets a v2 environment (e.g. `env.v2-demo`) via `AitoV2Client`, and
- creates each table as a v2 **collection** (`type: "collection"`) rather
  than a legacy table — collections are what unlock `relate`/`$patterns`.

The schema is a near-mechanical translation of `data_loader.SCHEMAS`:
the column maps (types, `link`, `nullable`) carry over unchanged; only
the table kind differs. The v1 loader and the live v1 demo are untouched.

A branched env inherits master's *legacy* tables, so building a
same-named collection first requires dropping the legacy table of that
name in the env. `--reset` does that; it is destructive within the
(isolated, re-branchable) env and will prompt for confirmation.

Usage:
    python -m src.data_loader_v2 --env env.v2-demo [--reset]
    python -m src.data_loader_v2 --env env.v2-demo --only invoices --customer CUST-0000
"""

import argparse
import sys

from src.aito_v2_client import AitoV2Client, AitoV2Error
from src.config import load_config
from src.data_loader import SCHEMAS, load_fixture

# Parent-first: a collection's `link` targets must already exist when it
# is created, so linked-to tables come earlier in the list.
CREATE_ORDER = [
    "customers",
    "corporate_entities",
    "employees",
    "help_articles",
    "invoices",
    "bank_transactions",
    "overrides",
    "help_impressions",
]

# Tables that have a fixture file to load (others are schema-only).
FIXTURE_TABLES = {
    "customers", "corporate_entities", "employees", "help_articles",
    "invoices", "bank_transactions", "overrides", "help_impressions",
}


def drop_existing(client: AitoV2Client, names: list[str]) -> None:
    """Drop collections/legacy tables, child-first, best-effort.

    A missing collection currently answers DELETE with a 500 (not 404),
    so we treat any error as "wasn't there / can't drop" and report it
    rather than aborting the whole build.
    """
    for name in reversed(names):
        try:
            client.delete_collection(name)
            print(f"  dropped '{name}'")
        except AitoV2Error as exc:
            print(f"  (skip drop '{name}': {exc.status_code})")


def create_collections(client: AitoV2Client, names: list[str]) -> None:
    """Create each table as a v2 collection from the shared schema."""
    for name in names:
        columns = SCHEMAS[name]["columns"]
        client.create_collection(name, columns)
        print(f"  created collection '{name}'")


def load_collections(
    client: AitoV2Client, names: list[str], customer: str | None = None
) -> int:
    """Load fixtures into the collections. Returns total rows inserted."""
    total = 0
    for name in names:
        if name not in FIXTURE_TABLES:
            continue
        rows = load_fixture(name)
        if customer and name == "invoices":
            rows = [r for r in rows if r.get("customer_id") == customer]
        inserted = client.insert_batch(name, rows)
        total += inserted
        print(f"  loaded {inserted} rows into '{name}'")
    return total


def optimize_collections(client: AitoV2Client, names: list[str]) -> None:
    """Rebuild each collection's index — required for predict quality.

    Without this, `predict` on a freshly loaded collection returns
    near-flat posteriors (see `AitoV2Client.optimize`). `relate`/
    `$patterns` are unaffected, but the demo's prediction paths need it.
    """
    for name in names:
        if name not in FIXTURE_TABLES:
            continue
        client.optimize(name)
        print(f"  optimized '{name}'")


def build(
    client: AitoV2Client,
    tables: list[str],
    *,
    customer: str | None = None,
    reset: bool = False,
) -> None:
    """Create and load the requested collections in dependency order."""
    order = [t for t in CREATE_ORDER if t in tables]
    if reset:
        print("Dropping existing tables/collections in the env...")
        drop_existing(client, order)
    print("Creating collections...")
    create_collections(client, order)
    print("Loading data...")
    total = load_collections(client, order, customer=customer)
    print("Optimizing collections (required for predict quality)...")
    optimize_collections(client, order)
    print(f"Done. Loaded {total} rows into env '{client._env}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the dataset as v2 collections.")
    parser.add_argument("--env", required=True, help="target environment, e.g. env.v2-demo")
    parser.add_argument("--only", help="comma-separated subset of tables to build")
    parser.add_argument("--customer", help="filter invoices to one customer_id (fast slice)")
    parser.add_argument("--reset", action="store_true", help="drop existing tables first")
    args = parser.parse_args()

    config = load_config()
    client = AitoV2Client(config.aito_api_url, config.aito_api_key, env=args.env)

    tables = args.only.split(",") if args.only else list(CREATE_ORDER)
    unknown = [t for t in tables if t not in SCHEMAS]
    if unknown:
        print(f"Unknown tables: {unknown}. Known: {sorted(SCHEMAS)}", file=sys.stderr)
        sys.exit(1)

    scope = f" (invoices → {args.customer})" if args.customer else ""
    print(f"Building {tables} as collections in '{args.env}'{scope}")
    build(client, tables, customer=args.customer, reset=args.reset)


if __name__ == "__main__":
    main()
