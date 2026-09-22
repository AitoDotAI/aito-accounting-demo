"""Coding a statement line that settles no invoice. See ADR 0024."""

import pytest

from src.bankfeed_service import REVIEW_THRESHOLD, code_all, code_bank_line


class FakePredictClient:
    """Canned `_query` response; records the request body."""

    def __init__(self, hits, rows=None):
        self._hits = hits
        self._rows = rows or []
        self.last_body: dict | None = None

    def _request(self, method, path, json=None, timeout=120.0):
        self.last_body = json
        return {"hits": self._hits}

    def search(self, table, where, limit=10):
        self.last_search = {"table": table, "where": where, "limit": limit}
        return {"hits": self._rows}


def _why():
    return {
        "type": "product",
        "factors": [
            {"type": "baseP", "value": 0.2, "proposition": {"gl_code": {"$has": "4500"}}},
            {"type": "relatedPropositionLift", "value": 6.0,
             "proposition": {"description": {"$has": "KORTTIMAKSUT"}}},
        ],
    }


_TXN = {
    "txn_id": "CUST-0000-TXN-009000",
    "customer_id": "CUST-0000",
    "description": "KORTTIMAKSUT TILITYS  19.04.25",
    "amount": 120.0,
    "amount_band": "small",
    "bank": "OP Bank",
}


class TestTheAmountBandIsSent:
    """Aito will not condition on a raw Decimal.

    Without the band the coder returns the counterparty's most common GL
    whatever the size: a card settlement came back 4100 at both EUR 120
    and EUR 4800, where the truth flips at the small/medium boundary.
    """

    def test_band_is_included_in_the_where(self):
        client = FakePredictClient([{"$value": "4500", "$p": 0.8, "$why": _why()}])

        code_bank_line(client, _TXN)

        assert client.last_body["where"]["amount_band"] == "small"
        assert client.last_body["where"]["amount"] == 120.0

    def test_a_line_without_a_band_still_codes(self):
        """Absent is not the same as wrong — omit the clause, don't guess."""
        client = FakePredictClient([{"$value": "4500", "$p": 0.8, "$why": _why()}])

        code_bank_line(client, {**_TXN, "amount_band": None})

        assert "amount_band" not in client.last_body["where"]


class TestLowConfidenceAsksForAHuman:
    def test_below_threshold_is_flagged_for_review(self):
        client = FakePredictClient([{"$value": "4500", "$p": REVIEW_THRESHOLD - 0.01,
                                     "$why": _why()}])

        line = code_bank_line(client, _TXN)

        assert line.status == "needs_review"

    def test_at_threshold_is_coded(self):
        client = FakePredictClient([{"$value": "4500", "$p": REVIEW_THRESHOLD,
                                     "$why": _why()}])

        assert code_bank_line(client, _TXN).status == "coded"


class TestOnlyUninvoicedLines:
    def test_the_search_asks_for_lines_with_no_invoice(self):
        """A line that settles an invoice belongs to Payment Matching.
        Pulling it in here would put one row on two pages answering two
        different questions."""
        client = FakePredictClient([], rows=[])

        code_all(client, "CUST-0000")

        assert client.last_search["where"]["invoice_id"] is None
        assert client.last_search["where"]["customer_id"] == "CUST-0000"


class TestOutputShape:
    def test_alternatives_and_label_are_carried(self):
        client = FakePredictClient([
            {"$value": "4500", "$p": 0.7, "$why": _why()},
            {"$value": "4100", "$p": 0.2, "$why": _why()},
        ])

        line = code_bank_line(client, _TXN)

        assert line.gl_label == "Office Expenses"
        assert line.alternatives[0]["gl_code"] == "4100"
        assert line.explanation, "the why factors must survive to the panel"

    def test_no_hits_returns_none_rather_than_a_fabricated_code(self):
        assert code_bank_line(FakePredictClient([]), _TXN) is None
