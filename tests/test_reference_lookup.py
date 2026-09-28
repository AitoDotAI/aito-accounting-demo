"""A quoted reference is a lookup; only unreferenced payments reach Aito.

The bank descriptions here are the formats the fixture banks actually
produce (see `format_bank_description` in data/generate_fixtures.py).
"""

import pytest

from src.matching_service import choose_payments_to_show, match_all, match_reference_first
from src.reference_lookup import find_invoice_by_reference, quotes_reference


class TestQuotesReference:
    @pytest.mark.parametrize("description", [
        "KARDEX FINLAND  Saaja  VIITE 468883814  10.05.25",   # Handelsbanken
        "OY BOTNIA-FOTO AB VANTAA 24022026 Viite: 468883814",  # Nordea
        "KARDEX FINLAND\t10.05.25\tref=VIITE 468883814",       # Aktia
        "DB-FIN KARDEX FINLAND OY 468883814",                  # Danske, label dropped
    ])
    def test_each_banks_format_of_a_viite_counts_as_quoted(self, description):
        assert quotes_reference(description, "VIITE 468883814")

    def test_an_rf_reference_split_across_spaces_counts_as_quoted(self):
        assert quotes_reference("SECURITY VENTURE OY RF18 1234 5678 9012", "RF18 1234 5678 9012")

    def test_a_description_without_the_reference_does_not_quote_it(self):
        assert not quotes_reference("DB-FIN KARDEX FINLAND OY", "VIITE 434735925")

    def test_digits_inside_a_longer_number_are_not_a_quote(self):
        # Reference 2402 appears inside the date 24022026, which is not
        # the payer quoting it.
        assert not quotes_reference("BOTNIA-FOTO VANTAA 24022026", "VIITE 2402")

    def test_a_reference_with_no_number_is_rejected_loudly(self):
        with pytest.raises(ValueError, match="no reference number"):
            quotes_reference("ANYTHING", "VIITE")


class TestFindInvoiceByReference:
    LEDGER = [
        {"invoice_id": "INV-1", "vendor": "Kardex", "amount": 100.0, "reference": "VIITE 468883814"},
        {"invoice_id": "INV-2", "vendor": "Kardex", "amount": 200.0, "reference": "VIITE 434735925"},
    ]

    def test_returns_the_invoice_whose_reference_is_quoted(self):
        found = find_invoice_by_reference("KARDEX / VIITE 434735925 / PVM 01.02.26", self.LEDGER)
        assert found["invoice_id"] == "INV-2"

    def test_returns_none_when_no_open_invoice_is_quoted(self):
        assert find_invoice_by_reference("KARDEX / VIITE 999999998", self.LEDGER) is None

    def test_quoting_two_open_invoices_is_a_data_error(self):
        with pytest.raises(ValueError, match="INV-1, INV-2"):
            find_invoice_by_reference("VIITE 468883814 VIITE 434735925", self.LEDGER)


class NoPredictClient:
    """Fails the test if the matcher asks Aito to predict anything."""

    def _request(self, method, path, json=None, timeout=120.0):
        raise AssertionError(f"reference lookup must not call Aito, but sent {path}")


class TestMatchReferenceFirst:
    TXN = {"txn_id": "T-1", "description": "KARDEX / VIITE 468883814",
           "amount": 100.0, "bank": "OP Bank", "customer_id": "CUST-0000"}

    def test_a_quoted_reference_is_matched_without_a_prediction(self):
        pair = match_reference_first(NoPredictClient(), self.TXN, TestFindInvoiceByReference.LEDGER)

        assert pair.invoice_id == "INV-1"
        assert pair.matched_by == "reference"
        assert pair.confidence == 1.0
        assert pair.explanation == [], "no prediction was made, so there is nothing to explain"

    def test_an_unreferenced_payment_is_sent_to_aito(self):
        class PredictClient:
            def _request(self, method, path, json=None, timeout=120.0):
                return {"hits": [{"invoice_id": "INV-2", "vendor": "Kardex", "amount": 200.0, "$p": 0.6}]}

        txn = {**self.TXN, "description": "DB-FIN KARDEX FINLAND OY", "amount": 200.0}
        pair = match_reference_first(PredictClient(), txn, TestFindInvoiceByReference.LEDGER)

        assert pair.invoice_id == "INV-2"
        assert pair.matched_by == "aito"


def _payment(n: int, invoice_id: str, description: str) -> dict:
    return {"transaction_id": f"T-{n}", "invoice_id": invoice_id, "description": description,
            "amount": 100.0, "bank": "OP Bank", "vendor_name": "Kardex"}


def _invoice(invoice_id: str, reference: str) -> dict:
    return {"invoice_id": invoice_id, "vendor": "Kardex", "amount": 100.0, "reference": reference}


class TestChoosePaymentsToShow:
    def test_unreferenced_payments_come_first_then_a_few_referenced(self):
        invoices = {f"INV-{i}": _invoice(f"INV-{i}", f"VIITE 10000{i}") for i in range(6)}
        payments = [
            _payment(0, "INV-0", "KARDEX VIITE 100000"),
            _payment(1, "INV-1", "KARDEX / PVM 01.02.26"),
            _payment(2, "INV-2", "KARDEX VIITE 100002"),
            _payment(3, "INV-3", "KARDEX / PVM 02.02.26"),
            _payment(4, "INV-4", "KARDEX VIITE 100004"),
            _payment(5, "INV-5", "KARDEX / PVM 03.02.26"),
        ]

        shown = choose_payments_to_show(payments, invoices, unreferenced=2, referenced=1)

        assert [p["transaction_id"] for p in shown] == ["T-1", "T-3", "T-0"]


class FakeLedgerClient:
    """Serves `_search` from fixed rows and `_predict` with the true invoice."""

    def __init__(self, payments, invoices):
        self.payments, self.invoices = payments, invoices
        self.predicted_descriptions: list[str] = []

    def search(self, table, where, limit=10):
        if table == "bank_transactions":
            return {"hits": self.payments[:limit]}
        wanted = where.get("invoice_id", {}).get("$or")
        rows = [r for r in self.invoices if wanted is None or r["invoice_id"] in wanted]
        return {"hits": rows[:limit]}

    def _request(self, method, path, json=None, timeout=120.0):
        description = json["where"]["description"]
        self.predicted_descriptions.append(description)
        truth = next(p["invoice_id"] for p in self.payments if p["description"] == description)
        row = next(r for r in self.invoices if r["invoice_id"] == truth)
        return {"hits": [{**row, "$p": 0.7}]}


class TestMatchAll:
    def _client(self):
        invoices = [_invoice(f"INV-{i}", f"VIITE 20000{i}") for i in range(4)]
        payments = [
            _payment(0, "INV-0", "KARDEX VIITE 200000"),
            _payment(1, "INV-1", "KARDEX / PVM 01.02.26"),
            _payment(2, "INV-2", "KARDEX VIITE 200002"),
            _payment(3, "INV-3", "KARDEX / PVM 02.02.26"),
        ]
        return FakeLedgerClient(payments, invoices)

    def test_only_unreferenced_payments_are_sent_to_aito(self):
        client = self._client()

        match_all(client, "CUST-0000", unreferenced_count=2, referenced_count=2)

        assert client.predicted_descriptions == ["KARDEX / PVM 01.02.26", "KARDEX / PVM 02.02.26"]

    def test_metrics_count_lookups_and_predictions_separately(self):
        result = match_all(self._client(), "CUST-0000", unreferenced_count=2, referenced_count=2)

        assert [p["matched_by"] for p in result["pairs"]] == ["aito", "aito", "reference", "reference"]
        assert result["metrics"]["matched_by_aito"] == 2
        assert result["metrics"]["matched_by_reference"] == 2

    def test_average_confidence_excludes_the_lookups_certainty(self):
        result = match_all(self._client(), "CUST-0000", unreferenced_count=2, referenced_count=2)

        aito_confidences = [p["confidence"] for p in result["pairs"] if p["matched_by"] == "aito"]
        assert result["metrics"]["avg_confidence"] == round(sum(aito_confidences) / 2, 2)
