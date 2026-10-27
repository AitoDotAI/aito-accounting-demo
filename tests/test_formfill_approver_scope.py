"""Form Fill offers only the customer's own staff as approver (td-20260901082623647538).

`customer_id` in a predict's `where` is evidence about the invoice. It does
not limit which employees Aito may rank, because `approver` links to
`employees` and the candidates come from the whole table. On shared Aito
2.11.9, with Form Fill's old query, CUST-0127 (one approver) was offered
CUST-0046-EMP-0001 and CUST-0046-EMP-0002 as alternatives, CUST-0007 was
offered CUST-0060-EMP-0002 and CUST-0100 CUST-0173-EMP-0000. Only a filter
on the linked row, `approver.customer_id`, limits the candidates.
"""

import pytest

from src.formfill_service import predict_fields

TENANT = "CUST-0127"
STAFF = {f"{TENANT}-EMP-0000": "Matti Laitinen"}


class RecordingClient:
    """Answers every predict with the tenant's one approver and records each body."""

    def __init__(self):
        self.wheres: dict[str, dict] = {}

    def predict(self, table, where, field, **kw):
        self.wheres[field] = dict(where)
        value = f"{TENANT}-EMP-0000" if field == "approver" else "x"
        return {"hits": [{"feature": value, "$p": 0.95, "$why": None}]}

    def search(self, table, where, limit=10):
        return {"hits": [{"employee_id": k, "name": v} for k, v in STAFF.items()]}


def test_the_approver_predict_is_limited_to_the_customers_own_staff():
    client = RecordingClient()
    predict_fields(client, {"customer_id": TENANT, "vendor": "Kardex Finland Oy"})
    assert client.wheres["approver"]["approver.customer_id"] == TENANT


def test_no_other_field_gets_the_employee_filter():
    client = RecordingClient()
    predict_fields(client, {"customer_id": TENANT, "vendor": "Kardex Finland Oy"})
    others = [w for field, w in client.wheres.items() if field != "approver"]
    assert others and all("approver.customer_id" not in w for w in others)


def test_approver_alternatives_show_the_name_not_the_employee_id():
    client = RecordingClient()
    result = predict_fields(client, {"customer_id": TENANT, "vendor": "Kardex Finland Oy"})
    approver = next(f for f in result["fields"] if f["field"] == "approver")
    assert [a["display"] for a in approver["alternatives"]] == ["Matti Laitinen"]
    assert [a["value"] for a in approver["alternatives"]] == [f"{TENANT}-EMP-0000"]


def test_an_approver_is_never_predicted_without_a_customer():
    # Without a customer there is no staff to limit the candidates to, and
    # every tenant's employees would compete.
    with pytest.raises(ValueError, match="needs a customer_id"):
        predict_fields(RecordingClient(), {"vendor": "Kardex Finland Oy"})
