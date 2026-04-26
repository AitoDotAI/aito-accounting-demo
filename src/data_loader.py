"""Upload data to Aito.

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

# Multi-tenant schema — all tables have customer_id for isolation.
# Links connect tables for _match and _predict traversal.
SCHEMAS = {
    "customers": {
        "type": "table",
        "columns": {
            "customer_id": {"type": "String", "nullable": False},
            "name": {"type": "String", "nullable": False},
            "size_tier": {"type": "String", "nullable": False},
            "invoice_count": {"type": "Int", "nullable": False},
            "employee_count": {"type": "Int", "nullable": False},
        },
    },
    "corporate_entities": {
        "type": "table",
        "columns": {
            "business_id": {"type": "String", "nullable": False},
            "name": {"type": "Text", "nullable": False},
            "industry_code": {"type": "String", "nullable": True},
            "industry": {"type": "String", "nullable": True},
            "city": {"type": "String", "nullable": True},
        },
    },
    "employees": {
        "type": "table",
        "columns": {
            "employee_id": {"type": "String", "nullable": False},
            "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
            "name": {"type": "String", "nullable": False},
            "role": {"type": "String", "nullable": False},
            "department": {"type": "String", "nullable": False},
            "supervisor_id": {"type": "String", "nullable": True, "link": "employees.employee_id"},
            "active": {"type": "Boolean", "nullable": False},
        },
    },
    "invoices": {
        "type": "table",
        "columns": {
            "invoice_id": {"type": "String", "nullable": False},
            "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
            "vendor_business_id": {"type": "String", "nullable": False, "link": "corporate_entities.business_id"},
            "vendor": {"type": "String", "nullable": False},
            "vendor_country": {"type": "String", "nullable": False},
            "category": {"type": "String", "nullable": False},
            "amount": {"type": "Decimal", "nullable": False},
            "gl_code": {"type": "String", "nullable": False},
            "cost_centre": {"type": "String", "nullable": False},
            "approver": {"type": "String", "nullable": False},
            "processor": {"type": "String", "nullable": False, "link": "employees.employee_id"},
            "vat_pct": {"type": "Int", "nullable": False},
            "payment_method": {"type": "String", "nullable": False},
            "due_days": {"type": "Int", "nullable": False},
            "description": {"type": "Text", "nullable": False},
            "invoice_date": {"type": "String", "nullable": False},
            "routed": {"type": "Boolean", "nullable": False},
            "routed_by": {"type": "String", "nullable": False},
        },
    },
    "bank_transactions": {
        "type": "table",
        "columns": {
            "transaction_id": {"type": "String", "nullable": False},
            "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
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
            "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
            "invoice_id": {"type": "String", "nullable": False, "link": "invoices.invoice_id"},
            "field": {"type": "String", "nullable": False},
            "predicted_value": {"type": "String", "nullable": False},
            "corrected_value": {"type": "String", "nullable": False},
            "confidence_was": {"type": "Decimal", "nullable": False},
            "corrected_by": {"type": "String", "nullable": False},
        },
    },
    "prediction_log": {
        "type": "table",
        "columns": {
            "log_id": {"type": "String", "nullable": False},
            "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
            "field": {"type": "String", "nullable": False},
            "predicted_value": {"type": "String", "nullable": True},
            "user_value": {"type": "String", "nullable": True},
            "source": {"type": "String", "nullable": False},  # "user" / "predicted" / "derived"
            "confidence": {"type": "Decimal", "nullable": False},
            "accepted": {"type": "Boolean", "nullable": False},
            "timestamp": {"type": "Int", "nullable": False},
        },
    },
}

# Table deletion order — linked tables first
DELETE_ORDER = ["prediction_log", "overrides", "bank_transactions", "invoices", "employees", "customers", "corporate_entities", "cache_entries"]


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
    batch_size = 1000
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        client._request("POST", f"/data/{table_name}/batch", json=batch)
        uploaded = min(i + batch_size, total)
        if uploaded % 10000 == 0 or uploaded == total:
            print(f"  Uploaded {uploaded}/{total} records to '{table_name}'")


def optimize_table(client: AitoClient, table_name: str) -> None:
    """Optimize an Aito table for faster query performance.

    Aito's optimize endpoint compacts the table's index, which speeds up
    _predict, _relate, and _evaluate queries. Should be run after bulk
    uploads when the table won't change for a while.
    """
    print(f"  Optimizing '{table_name}'...")
    try:
        # Aito's optimize endpoint requires an empty JSON body
        client._request("POST", f"/data/{table_name}/optimize", json={})
    except AitoError as exc:
        # Optimize is best-effort — don't fail upload if it errors
        print(f"    optimize warning: {exc}")


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
        for table_name in DELETE_ORDER:
            delete_table(client, table_name)

    print("\nCreating schemas...")
    for table_name, schema in SCHEMAS.items():
        create_schema(client, table_name, schema)

    # Load and upload each table that has fixture data
    print("\nUploading data...")
    fixture_names = ["customers", "corporate_entities", "employees", "invoices", "bank_transactions", "overrides"]
    total_records = 0
    uploaded_tables = []
    for table_name in fixture_names:
        try:
            records = load_fixture(table_name)
            upload_data(client, table_name, records)
            total_records += len(records)
            uploaded_tables.append(table_name)
        except FileNotFoundError:
            print(f"  Skipping '{table_name}' (no fixture file)")

    # Optimize tables for faster query performance after bulk upload
    print("\nOptimizing tables...")
    for table_name in uploaded_tables:
        optimize_table(client, table_name)

    print(f"\nDone. Loaded {total_records} total records.")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    run(reset=reset)
