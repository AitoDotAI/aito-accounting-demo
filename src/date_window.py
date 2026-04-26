"""Frozen demo time.

The dataset spans 2024-05-01 to 2026-04-30. We freeze the demo's
"today" to DEMO_TODAY so every visitor sees the same data — overdue
invoices look overdue, due-soon look due-soon, regardless of when
the page is loaded.

Frontend reads `/api/demo/today` and uses it everywhere it would
otherwise call `new Date()`. Server uses `demo_today()` for any
date math (e.g. due-date calculations).

The dataset never goes stale, every screenshot is reproducible, and
the demo behaves like a permanent snapshot of accounting history.
"""

from datetime import date

# Pinned to the last day of the dataset window.
DEMO_TODAY = date(2026, 4, 30)


def demo_today() -> date:
    """The frozen 'now' for the demo."""
    return DEMO_TODAY


def shift_iso(iso_date: str | None) -> str | None:
    """Pass-through: dates are stored as-is in Aito; no shift needed.

    Kept as a thin wrapper so callers don't need to know that we
    moved from rolling-window to frozen-time.
    """
    return iso_date


def shift_invoice(invoice: dict) -> dict:
    """Return the invoice unchanged (kept for API compatibility)."""
    return invoice
