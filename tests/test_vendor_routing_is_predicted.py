"""The home page's per-tenant answer is a _predict, with its evidence.

It used to be the most common routing among the vendor's last 50 invoices
(`_search` + a Counter): no probability, no $why, nothing Aito-specific to
show. Now each tenant's GL account, approver and cost centre are predicted
for the vendor, and each answer carries its probability and its $why.
"""

from src.vendor_routing import predict_vendor_routing

# A tenant id no other test uses: the employee directory caches per tenant.
CUSTOMER = "CUST-9102"
WHY = {"type": "product", "factors": [
    {"type": "baseP", "value": 0.2, "proposition": {"gl_code": {"$has": "4400"}}},
    {"type": "relatedPropositionLift", "value": 3.5,
     "proposition": {"vendor": {"$has": "Kardex Finland Oy"}}},
]}


class PredictClient:
    def __init__(self, top_p=0.7):
        self.top_p = top_p
        self.predicted = []  # (where, field)

    def predict(self, table, where, field, **_):
        self.predicted.append((dict(where), field))
        value = {"gl_code": "4400", "approver": f"{CUSTOMER}-EMP-0009", "cost_centre": "CC-100"}[field]
        return {"hits": [{"feature": value, "$p": self.top_p, "$why": WHY},
                         {"feature": "other", "$p": 0.2}]}

    def search(self, table, where, limit=10):
        return {"hits": [{"employee_id": f"{CUSTOMER}-EMP-0009", "name": "Maria Nieminen"}]}


def test_the_gl_account_is_a_prediction_with_its_probability():
    routing = predict_vendor_routing(PredictClient(), CUSTOMER, "Kardex Finland Oy")

    assert routing["gl_code"]["value"] == "4400"
    assert routing["gl_code"]["p"] == 0.7


def test_the_gl_account_carries_the_why_that_explains_it():
    routing = predict_vendor_routing(PredictClient(), CUSTOMER, "Kardex Finland Oy")

    why = routing["gl_code"]["why"]
    assert any(f["type"] == "base" for f in why)
    assert any(f["type"] == "pattern" and f["lift"] == 3.5 for f in why)


def test_the_approver_is_predicted_and_shown_by_name():
    routing = predict_vendor_routing(PredictClient(), CUSTOMER, "Kardex Finland Oy")

    assert routing["approver"]["display"] == "Maria Nieminen"
    assert routing["approver"]["value"] == f"{CUSTOMER}-EMP-0009"


def test_every_prediction_is_made_for_this_tenant_and_vendor():
    client = PredictClient()
    predict_vendor_routing(client, CUSTOMER, "Kardex Finland Oy")

    assert {f for _, f in client.predicted} >= {"gl_code", "approver", "cost_centre"}
    for where, _ in client.predicted:
        assert where["customer_id"] == CUSTOMER and where["vendor"] == "Kardex Finland Oy"


def test_the_approver_candidates_are_limited_to_the_tenants_staff():
    client = PredictClient()
    predict_vendor_routing(client, CUSTOMER, "Kardex Finland Oy")

    approver_where = next(w for w, f in client.predicted if f == "approver")
    assert approver_where["approver.customer_id"] == CUSTOMER


def test_a_tenant_with_no_confident_prediction_gets_none():
    # Below Aito's noise floor the answer is "not enough history", not a guess.
    assert predict_vendor_routing(PredictClient(top_p=0.05), CUSTOMER, "Kardex Finland Oy") is None


def test_each_answer_shows_the_why_of_the_hit_it_came_from():
    # The approver is asked with the tenant filter inside the same query, so
    # the top hit and its $why are Aito's for that scoped question; nothing is
    # promoted from a runner-up and paired with another hit's evidence.
    def why_with_lift(lift):
        return {"type": "product", "factors": [
            {"type": "relatedPropositionLift", "value": lift, "proposition": {"vendor": {"$has": "X"}}}]}

    class Client(PredictClient):
        def predict(self, table, where, field, **_):
            self.predicted.append((dict(where), field))
            if field == "approver":
                assert where["approver.customer_id"] == CUSTOMER
                return {"hits": [{"feature": f"{CUSTOMER}-EMP-0009", "$p": 0.6, "$why": why_with_lift(7.0)},
                                 {"feature": f"{CUSTOMER}-EMP-0010", "$p": 0.2, "$why": why_with_lift(2.0)}]}
            return super().predict(table, where, field)

    routing = predict_vendor_routing(Client(), CUSTOMER, "Kardex Finland Oy")

    assert routing["approver"]["value"] == f"{CUSTOMER}-EMP-0009"
    assert [f["lift"] for f in routing["approver"]["why"] if f["type"] == "pattern"] == [7.0]
