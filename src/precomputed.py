"""Per-customer precompute reads — thin wrapper over precompute_store.

Historically this module read straight from
`data/precomputed/{customer_id}/{name}.json`. After the precompute
store landed (PR #7), per-customer outputs go through the same
3-layer path (L1 → Aito `precompute_entries` → bootstrap file)
that landing/help_related use.

Keeping the wrapper so existing endpoint code (`precomputed.load`,
`precomputed.has`) doesn't churn — and so anyone grep'ing for
"precomputed" still finds the right module.
"""

from typing import Any

from src import precompute_store


def load(customer_id: str, name: str) -> dict | None:
    """Read precompute output for (customer_id, name)."""
    return precompute_store.get(precompute_store.per_customer_key(customer_id, name))


def has(customer_id: str, name: str) -> bool:
    return load(customer_id, name) is not None
