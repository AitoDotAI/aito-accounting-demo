"""A form-fill template names its approver, and applies its employee id.

The quick-start cards used to print "Hyväksyjä: CUST-0001-EMP-0009" -- the
key the invoice is stored against, not a person anyone recognises.
"""

from src.formfill_service import predict_template

# A tenant id no other test uses: the employee directory caches per tenant.
CUSTOMER = "CUST-9101"


class TemplateClient:
    def search(self, table, where, limit=10):
        if table == "employees":
            return {"hits": [{"employee_id": f"{CUSTOMER}-EMP-0009", "name": "Maria Nieminen"}]}
        invoice = {"gl_code": "4400", "approver": f"{CUSTOMER}-EMP-0009", "cost_centre": "CC-1"}
        return {"hits": [dict(invoice) for _ in range(5)]}


def test_the_template_shows_the_approvers_name():
    template = predict_template(TemplateClient(), CUSTOMER, "Kardex Finland Oy")

    assert template["fields"]["approver_name"] == "Maria Nieminen"


def test_applying_the_template_still_submits_the_employee_id():
    # The id is unique where a name is not, so it is what gets recorded.
    template = predict_template(TemplateClient(), CUSTOMER, "Kardex Finland Oy")

    assert template["fields"]["approver"] == f"{CUSTOMER}-EMP-0009"
