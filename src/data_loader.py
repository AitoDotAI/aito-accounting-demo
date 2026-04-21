"""Upload sample data to Aito.

Creates table schemas and uploads fixture data. Designed to be
idempotent — safe to run multiple times.

Usage: python -m src.data_loader [--reset]
"""

import json
import sys
from pathlib import Path

from src.aito_client import AitoClient, AitoError
from src.config import load_config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Aito table schemas — field types match the fixture data.
# Aito infers relationships automatically; we just declare types.
SCHEMAS = {
    "invoices": {
        "type": "table",
        "columns": {
            "invoice_id": {"type": "String", "nullable": False},
            "vendor": {"type": "String", "nullable": False},
            "vendor_country": {"type": "String", "nullable": False},
            "category": {"type": "String", "nullable": False},
            "amount": {"type": "Decimal", "nullable": False},
            "gl_code": {"type": "String", "nullable": False},
            "cost_centre": {"type": "String", "nullable": False},
            "approver": {"type": "String", "nullable": False},
            "vat_pct": {"type": "Int", "nullable": False},
            "payment_method": {"type": "String", "nullable": False},
            "due_days": {"type": "Int", "nullable": False},
            "description": {"type": "Text", "nullable": False},
            "routed": {"type": "Boolean", "nullable": False},
            "routed_by": {"type": "String", "nullable": False},
        },
    },
    "bank_transactions": {
        "type": "table",
        "columns": {
            "transaction_id": {"type": "String", "nullable": False},
            "description": {"type": "Text", "nullable": False},
            "vendor_name": {"type": "Text", "nullable": True},
            "amount": {"type": "Decimal", "nullable": False},
            "bank": {"type": "String", "nullable": False},
            "invoice_id": {"type": "String", "nullable": True, "link": "invoices.invoice_id"},
        },
    },
    "overrides": {
        "type": "table",
        "columns": {
            "override_id": {"type": "String", "nullable": False},
            "invoice_id": {"type": "String", "nullable": False, "link": "invoices.invoice_id"},
            "field": {"type": "String", "nullable": False},
            "predicted_value": {"type": "String", "nullable": False},
            "corrected_value": {"type": "String", "nullable": False},
            "confidence_was": {"type": "Decimal", "nullable": False},
            "corrected_by": {"type": "String", "nullable": False},
        },
    },
}


def load_fixture(name: str) -> list[dict]:
    """Load a JSON fixture file from the data directory."""
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Fixture file not found: {path}. "
            f"Run 'python data/generate_fixtures.py' first."
        )
    with open(path) as f:
        return json.load(f)


def create_schema(client: AitoClient, table_name: str, schema: dict) -> None:
    """Create or replace a table schema in Aito."""
    print(f"  Creating schema for '{table_name}'...")
    client._request("PUT", f"/schema/{table_name}", json=schema)


def upload_data(client: AitoClient, table_name: str, records: list[dict]) -> None:
    """Upload records to an Aito table in batches."""
    batch_size = 100
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        client._request("POST", f"/data/{table_name}/batch", json=batch)
        print(f"  Uploaded {min(i + batch_size, total)}/{total} records to '{table_name}'")


def delete_table(client: AitoClient, table_name: str) -> None:
    """Delete a table and its data from Aito."""
    print(f"  Deleting table '{table_name}'...")
    try:
        client._request("DELETE", f"/schema/{table_name}")
    except AitoError as exc:
        if exc.status_code == 404:
            print(f"  Table '{table_name}' does not exist, skipping.")
        else:
            raise


def run(reset: bool = False) -> None:
    """Main entry point for the data loader."""
    config = load_config()
    client = AitoClient(config)

    if not client.check_connectivity():
        print(f"Error: Cannot connect to Aito at {config.aito_api_url}")
        sys.exit(1)

    print(f"Connected to Aito at {config.aito_api_url}")

    if reset:
        print("\nResetting — deleting existing tables...")
        # Delete cache table first, then linked tables, then base tables
        delete_table(client, "prediction_cache")
        for table_name in reversed(list(SCHEMAS.keys())):
            delete_table(client, table_name)

    print("\nCreating schemas...")
    for table_name, schema in SCHEMAS.items():
        create_schema(client, table_name, schema)

    print("\nUploading data...")
    for table_name in SCHEMAS:
        records = load_fixture(table_name)
        upload_data(client, table_name, records)

    print(f"\nDone. Loaded {sum(len(load_fixture(t)) for t in SCHEMAS)} total records.")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    run(reset=reset)
