"""Smart Form Fill must use what the invoice says was bought, not only who
sent it.

It used to fill every field from the vendor alone: `description` was not
an accepted input, and `amount` reached Aito as a raw Decimal, which Aito
does not condition on. So payment method and due terms -- vendor master
data -- were the headline, and a vendor the tenant had never used got no
answer at all. Measured on CUST-0000 with the description and band:

  unseen vendor, "Annual software licence renewal"   None -> 6100 @ 0.78
  Kardex, "Printer paper and toner", small            4400 -> 4500 @ 0.92
"""

from src.amount_band import amount_band
from src.formfill_service import INPUT_FIELDS, predict_fields


class RecordingClient:
    def __init__(self):
        self.wheres = []

    def predict(self, table, where, field, **kw):
        self.wheres.append(dict(where))
        return {"hits": [{"feature": "6100", "$p": 0.78, "$why": None}]}

    def search(self, table, where, limit=10):
        return {"hits": []}  # the approver name directory


def test_description_is_an_accepted_input():
    assert "description" in INPUT_FIELDS


def test_the_amount_is_sent_as_a_band_aito_can_condition_on():
    c = RecordingClient()

    predict_fields(c, {"customer_id": "CUST-0000", "vendor": "Uusi Toimittaja Oy",
                       "description": "Annual software licence renewal", "amount": 4800})

    assert c.wheres and all(w.get("amount_band") == "medium" for w in c.wheres)
    assert all(w.get("description") == "Annual software licence renewal" for w in c.wheres)


def test_an_explicit_band_is_not_overridden():
    c = RecordingClient()

    predict_fields(c, {"customer_id": "CUST-0000", "vendor": "X", "amount": 4800,
                       "amount_band": "large"})

    assert all(w["amount_band"] == "large" for w in c.wheres)


def test_band_thresholds():
    assert amount_band(999.99) == "small"
    assert amount_band(1000) == "medium"
    assert amount_band(9999.99) == "medium"
    assert amount_band(10000) == "large"


def test_the_approver_is_shown_by_name_and_submitted_by_id(monkeypatch):
    """It rendered "CUST-0000-EMP-0015". The form submits the id, the person
    reading it needs the name."""
    from src import formfill_service
    monkeypatch.setattr(formfill_service, "tenant_employee_names",
                        lambda client, cid: {"CUST-0000-EMP-0015": "Markku Heikkinen"})

    class C:
        def predict(self, table, where, field, **kw):
            v = "CUST-0000-EMP-0015" if field == "approver" else "x"
            return {"hits": [{"feature": v, "$p": 0.95, "$why": None}]}

    out = predict_fields(C(), {"customer_id": "CUST-0000", "vendor": "Kardex Finland Oy"})
    approver = next(f for f in out["fields"] if f["field"] == "approver")

    assert approver["value"] == "Markku Heikkinen"
    assert approver["raw_value"] == "CUST-0000-EMP-0015"
