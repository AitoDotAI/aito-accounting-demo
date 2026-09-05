"""Tests for the payment matching service.

Tests verify invoice matching via _predict invoice_id (link traversal),
amount proximity scoring, and the matching pipeline.
"""

import pytest
import httpx

from src.aito_client import AitoClient
from src.config import Config
from src.matching_service import (
    _amount_match_score,
    _build_explanation,
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
    def _mock_predict_invoice(self, httpx_mock, invoice_id, vendor, amount, p=0.10):
        """Mock _predict invoice_id returning invoice rows via link."""
        httpx_mock.add_response(
            url="https://test.aito.app/db/demo/api/v1/_predict",
            json={"offset": 0, "total": 1, "hits": [
                {"$p": p, "invoice_id": invoice_id, "vendor": vendor,
                 "amount": amount, "$why": {"type": "product", "factors": []}},
            ]},
        )

    def test_direct_invoice_match(self, httpx_mock):
        """Aito returns an open invoice directly → matched."""
        self._mock_predict_invoice(httpx_mock, "INV-001", "Telia Finland", 890.50, 0.10)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-001", "description": "TELIA FINLAND OY", "amount": 890.50, "bank": "OP"},
            [{"invoice_id": "INV-001", "vendor": "Telia Finland", "amount": 890.50}],
        )

        assert pair is not None
        assert pair.invoice_id == "INV-001"
        assert pair.status == "matched"

    def test_vendor_match_different_invoice(self, httpx_mock):
        """Aito returns right vendor but different invoice → matches by vendor + amount."""
        self._mock_predict_invoice(httpx_mock, "INV-999", "SOK Corporation", 10000, 0.13)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-003", "description": "SOK CORPORATION", "amount": 7852.00, "bank": "Nordea"},
            [{"invoice_id": "INV-003", "vendor": "SOK Corporation", "amount": 7850.00}],
        )

        assert pair is not None
        assert pair.invoice_id == "INV-003"

    def test_no_matching_vendor_returns_none(self, httpx_mock):
        """Aito returns vendors not in open invoices → no match."""
        self._mock_predict_invoice(httpx_mock, "INV-999", "SAP SE", 5000, 0.05)

        client = AitoClient(TEST_CONFIG)
        pair = match_bank_txn_to_invoice(
            client,
            {"txn_id": "TXN-006", "description": "UNKNOWN TRANSFER", "amount": 550.00, "bank": "OP"},
            [{"invoice_id": "INV-004", "vendor": "Unknown Vendor GmbH", "amount": 3100.00}],
        )

        assert pair is None

    def test_aito_error_returns_none(self, httpx_mock):
        """If Aito fails, return None."""
        # Client retries once on connection error before giving up
        for _ in range(2):
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
        self._mock_predict_invoice(httpx_mock, "INV-999", "Telia Finland", 890.50, 0.10)

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


# ── Regressions from the 2026-09-04 live demo (ADR 0018) ────────────
#
# All three returned a 200 with a plausible-looking panel, so only an
# assertion on the CONTENT of the explanation catches them.


class FakePredictClient:
    """Returns a canned `_predict` response without any HTTP."""

    def __init__(self, hits):
        self._hits = hits

    def _request(self, method, path, json=None, timeout=120.0):
        return {"hits": self._hits}


def _why_for(invoice_id: str, lift: float = 8.0) -> dict:
    """A $why tree shaped like the one Aito returns for a predicted link."""
    return {
        "type": "product",
        "factors": [
            {"type": "baseP", "value": 7.8e-06,
             "proposition": {"invoice_id": {"$has": invoice_id}}},
            {"type": "relatedPropositionLift", "value": lift,
             "proposition": {"description": {"$has": "ACME"}}},
        ],
    }


_TXN = {
    "txn_id": "CUST-0000-TXN-000001",
    "description": "ACME OY VIITE 12345",
    "amount": 1000.0,
    "bank": "Nordea",
    "customer_id": "CUST-0000",
}


class TestExplanationBelongsToTheMatchedInvoice:
    """The defect that reached a live demo: another invoice's explanation.

    When Aito ranks an invoice that is not in the open ledger, the matcher
    substitutes a same-vendor invoice whose amount fits. It used to keep
    Aito's `$why` from the invoice it ranked, so the panel showed a base
    rate for an id that appeared nowhere on screen and labelled the
    payment's own description as counter-evidence.
    """

    def test_direct_match_keeps_aitos_explanation(self):
        client = FakePredictClient([
            {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
             "$p": 0.9, "$why": _why_for("INV-1")},
        ])
        pair = match_bank_txn_to_invoice(
            client, _TXN, [{"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0}])

        assert pair.invoice_id == "INV-1"
        base = next(f for f in pair.explanation if f["type"] == "base")
        assert base["target_value"] == "INV-1", "explanation must describe the matched invoice"

    def test_substituted_match_does_not_borrow_the_other_invoices_why(self):
        # Aito ranks INV-9 (absent from the ledger); we pair INV-2, same
        # vendor, whose amount fits the payment.
        client = FakePredictClient([
            {"invoice_id": "INV-9", "vendor": "ACME Oy", "amount": 250.0,
             "$p": 0.4, "$why": _why_for("INV-9")},
        ])
        pair = match_bank_txn_to_invoice(
            client, _TXN, [{"invoice_id": "INV-2", "vendor": "ACME Oy", "amount": 1000.0}])

        assert pair.invoice_id == "INV-2"
        targets = [f.get("target_value") for f in pair.explanation if f["type"] == "base"]
        assert "INV-9" not in targets, \
            "the substituted match must not present INV-9's explanation as its own"

    def test_substituted_match_says_it_was_substituted(self):
        client = FakePredictClient([
            {"invoice_id": "INV-9", "vendor": "ACME Oy", "amount": 250.0,
             "$p": 0.4, "$why": _why_for("INV-9")},
        ])
        pair = match_bank_txn_to_invoice(
            client, _TXN, [{"invoice_id": "INV-2", "vendor": "ACME Oy", "amount": 1000.0}])

        rendered = " ".join(
            p["value"] for f in pair.explanation for p in f.get("propositions", []))
        assert "INV-9" in rendered and "same vendor" in rendered, \
            "the panel should say the pairing came from the vendor, naming what Aito ranked"


class TestBaseRateSurvivesExtraction:
    def test_a_tiny_base_rate_is_not_flattened_to_zero(self):
        """A link-target base rate is ~1/128000 and was rounded to 0.0.

        That is what made the popup read "0% x 0.7 = 58%": the factor
        chain started from a literal zero.
        """
        explanation = _build_explanation(
            _TXN, {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0},
            0.9, _why_for("INV-1"))
        base = next(f for f in explanation if f["type"] == "base")
        assert base["base_p"] > 0
