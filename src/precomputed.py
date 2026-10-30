"""Per-customer precompute reads — thin wrapper over precompute_store.

Historically this module read straight from
`data/precomputed/{customer_id}/{name}.json`. After the precompute
store landed (PR #7), per-customer outputs go through the same
3-layer path (L1 → Aito `precompute_entries` → bootstrap file)
that landing/help_related use.

Keeping the wrapper so existing endpoint code (`precomputed.load`,
`precomputed.has`) doesn't churn — and so anyone grep'ing for
"precomputed" still finds the right module.

A precompute is also a cache of a *shape*, not only of numbers. When a
view starts reading a field the stored payload predates, the endpoint
serves the old payload — it is returned before anything is computed —
and the page renders a correct answer to the wrong question. That is
what "0 of 8 payments matched by Aito" was
(td-20260929184944220524): the matcher was fine and the payload simply
had no `matched_by` for the page to read. So a payload that is missing
the fields its page needs is refused here and the request falls through
to the live path, which is slower and right.
"""

from typing import Callable

from src import precompute_store


def _matching_pairs_staleness(payload: dict) -> str | None:
    """Why this payment-matching payload cannot be served, or None.

    `metrics.matched_by_aito` drives the headline tile and
    `pair.matched_by` labels every row (ADR 0026): without them the page
    cannot distinguish a prediction from a reference-number lookup, and
    says nothing was matched by Aito.
    """
    metrics = payload.get("metrics") or {}
    if "matched_by_aito" not in metrics:
        return "metrics.matched_by_aito is missing (predates ADR 0026)"
    pairs = payload.get("pairs") or []
    if pairs and not any("matched_by" in pair for pair in pairs):
        return "no pair carries matched_by (predates ADR 0026)"
    return None


# Only for outputs whose readers have moved on. A name absent from here
# is served unchanged: this is a guard against a known kind of drift, not
# a schema for every precompute.
STALENESS_CHECKS: dict[str, Callable[[dict], str | None]] = {
    "matching_pairs": _matching_pairs_staleness,
}

# One line per (customer, name), not per request: 255 tenants on every
# page load would bury the message in its own noise.
_warned: set[tuple[str, str]] = set()


def load(customer_id: str, name: str) -> dict | None:
    """Read precompute output for (customer_id, name).

    Returns None when nothing is stored, and also when what is stored is
    missing fields its page reads — the caller then computes live.
    """
    payload = precompute_store.get(precompute_store.per_customer_key(customer_id, name))
    if payload is None:
        return None

    check = STALENESS_CHECKS.get(name)
    if check is None:
        return payload

    stale = check(payload)
    if stale is None:
        return payload

    if (customer_id, name) not in _warned:
        _warned.add((customer_id, name))
        print(f"precompute {name} for {customer_id} ignored: {stale}. "
              f"Serving live; run ./do precompute-v2 to rebuild it.")
    return None


def has(customer_id: str, name: str) -> bool:
    return load(customer_id, name) is not None
