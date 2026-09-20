"""Resolving employee ids to the people behind them.

`invoices.approver` and `invoices.processor` both store an
`employee_id` and link to `employees`. Storing the id rather than the
name is what makes the link possible, and the link is what lets a
predict confine its candidates to one tenant with
`approver.customer_id`.

The cost is that a prediction comes back as `CUST-0000-EMP-0156`, which
is not what anyone wants to read. This module turns that back into
"Matti Niemi" at the point of display.

Resolved here rather than by selecting `approver.name` in the query,
because neither client's `predict` takes a custom `select` and v1 is
still the production path.
"""

from src.aito_client import AitoError

_cache: dict[str, dict[str, str]] = {}


def tenant_employee_names(client, customer_id: str, sample: int = 1000) -> dict[str, str]:
    """This customer's employee_id -> name.

    Cached per process for the life of the request batch: predicting 20
    invoices must not run 20 identical scans.

    Returns {} without a customer_id — a prediction that is not
    tenant-scoped has no roster to resolve against, and asking for one
    would be a wasted round trip.
    """
    if not customer_id:
        return {}
    cached = _cache.get(customer_id)
    if cached is not None:
        return cached
    try:
        rows = client.search("employees", {"customer_id": customer_id}, limit=sample)
    except AitoError:
        return {}
    names = {r["employee_id"]: r.get("name", r["employee_id"])
             for r in rows.get("hits", []) if r.get("employee_id")}
    _cache[customer_id] = names
    return names


def resolve(names: dict[str, str], employee_id: str | None) -> str | None:
    """Name for an id, falling back to the id itself.

    An employee who has left the roster still appears in history. Showing
    the raw id is ugly; dropping the value would lose a real prediction.
    """
    if not employee_id:
        return None
    return names.get(employee_id, employee_id)
