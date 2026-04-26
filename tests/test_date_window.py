"""Tests for the frozen demo time."""

from datetime import date

from src.date_window import DEMO_TODAY, demo_today, shift_invoice, shift_iso


class TestDemoToday:
    def test_demo_today_returns_pinned_date(self):
        assert demo_today() == DEMO_TODAY
        assert demo_today() == date(2026, 4, 30)

    def test_pinned_date_is_dataset_end(self):
        # The frozen date must match the fixture generator's END_DATE
        assert DEMO_TODAY == date(2026, 4, 30)


class TestShiftIso:
    def test_pass_through_for_valid_date(self):
        # Frozen-time mode: dates are stored as-is, no shift applied
        assert shift_iso("2025-01-01") == "2025-01-01"

    def test_pass_through_for_none(self):
        assert shift_iso(None) is None

    def test_pass_through_for_invalid(self):
        assert shift_iso("not-a-date") == "not-a-date"


class TestShiftInvoice:
    def test_returns_invoice_unchanged(self):
        inv = {"invoice_id": "INV-1", "invoice_date": "2025-06-15"}
        assert shift_invoice(inv) is inv
