"""Read pre-computed JSON files written by data/precompute_predictions.py.

For a hosted public demo we precompute every read-only view at
build/data-load time and serve the static JSON. The only live Aito
call from a browser session is the interactive Form Fill prediction.

Read endpoints fall back to live Aito if the precomputed file is
missing — this lets the dev workflow run against fresh data without
needing to precompute on every fixture change.
"""

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "precomputed"


def load(customer_id: str, name: str) -> dict | None:
    """Read data/precomputed/{customer_id}/{name}.json, or None if absent."""
    path = _DATA_DIR / customer_id / f"{name}.json"
    if not path.is_file():
        return None
    with open(path) as f:
        return json.load(f)


def has(customer_id: str, name: str) -> bool:
    return (_DATA_DIR / customer_id / f"{name}.json").is_file()
