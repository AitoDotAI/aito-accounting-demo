"""Tests for the payment matching service.

Tests verify vendor resolution via _predict on vendor_name,
amount proximity scoring, and the matching pipeline.
"""

import pytest
import httpx

from src.aito_client import AitoClient
from src.config import Config
from src.matching_service import (
    _amount_match_score,
    match_bank_txn_to_invoice,
    MatchPair,
)

TEST_CONFIG = Config(
    aito_api_url="https://test.aito.app/db/demo",
    aito_api_key="test-key",
)


class TestAmountMatchScore:
    def test_exact_amount(self):
        assert _amount_match_score(890.50, 890.50) == 1.0

    def test_within_half_percent(self):
        score = _amount_match_score(7850.00, 7852.00)
        assert score >= 0.90

    def test_within_two_percent(self):
        score = _amount_match_score(3100.00, 3099.00)
        assert score >= 0.80

    def test_large_difference_returns_zero(self):
        score = _amount_match_score(890.50, 4220.00)
        assert score == 0.0

    def test_zero_invoice_amount(self):
        assert _amount_match_score(0, 100) == 0.0


class TestMatchBankTxnToInvoice:
    def _mock_predict_response(self, httpx_mock, vendor, p=0.40):
        """Mock _predict on vendor_name returning a vendor."""
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": p, "$value": vendor, "$why": {"type": "product", "factors": []}},
            ]},
        )

    def test_exact_vendor_and_amount_match(self, httpx_mock):
        """_predict resolves vendor, exact amount → matched."""
        self._mock_predict_response(httpx_mock, "Telia Finland", 0.46)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-001", "description": "TELIA FINLAND OY", "amount": 890.50, "bank": "OP"},
            [{"invoice_id": "INV-001", "vendor": "Telia Finland", "amount": 890.50}],
        )

        assert pair is not None
        assert pair.status == "matched"
        assert pair.invoice_id == "INV-001"

    def test_vendor_match_with_amount_difference(self, httpx_mock):
        """_predict finds vendor, small amount diff → still matches."""
        self._mock_predict_response(httpx_mock, "SOK Corporation", 0.10)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-003", "description": "SOK CORPORATION", "amount": 7852.00, "bank": "Nordea"},
            [{"invoice_id": "INV-003", "vendor": "SOK Corporation", "amount": 7850.00}],
        )

        assert pair is not None
        assert pair.status in ("matched", "suggested")

    def test_no_matching_vendor_in_open_invoices(self, httpx_mock):
        """_predict returns vendor not in open invoices → no match."""
        self._mock_predict_response(httpx_mock, "SAP SE", 0.15)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-006", "description": "UNKNOWN TRANSFER", "amount": 550.00, "bank": "OP"},
            [{"invoice_id": "INV-004", "vendor": "Unknown Vendor GmbH", "amount": 3100.00}],
        )

        assert pair is None

    def test_aito_error_returns_none(self, httpx_mock):
        """If Aito _predict fails, return None."""
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://test.aito.app/db/demo/api/v1/_predict",
        )

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-001", "description": "TELIA", "amount": 890.50, "bank": "OP"},
            [{"invoice_id": "INV-001", "vendor": "Telia Finland", "amount": 890.50}],
        )

        assert pair is None

    def test_empty_open_invoices_returns_none(self, httpx_mock):
        self._mock_predict_response(httpx_mock, "Telia Finland", 0.45)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-001", "description": "TELIA", "amount": 890.50, "bank": "OP"},
            [],
        )

        assert pair is None


class TestMatchPair:
    def test_to_dict_includes_all_fields(self):
        pair = MatchPair(
            invoice_id="INV-001",
            invoice_vendor="Telia Finland",
            invoice_amount=890.50,
            bank_txn_id="TXN-001",
            bank_description="TELIA FINLAND OY",
            bank_amount=890.50,
            bank_name="OP Bank",
            confidence=0.95,
            status="matched",
        )
        d = pair.to_dict()

        assert d["invoice_id"] == "INV-001"
        assert d["bank_txn_id"] == "TXN-001"
        assert d["confidence"] == 0.95
        assert d["status"] == "matched"
        assert "explanation" in d
