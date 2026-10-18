"""Explanations keep the priors Aito reports through linked rows (ADR 0031 step A).

The shapes below are copied from shared Aito 2.11.6 (2026-10-18), a
CUST-0000 invoice from a software vendor, with `vendor_business_id` in
`where`:

- input side: the vendor lift carries the company's industry from the
  PRH register;
- target side: the approver lift carries the predicted employee's
  department and role.
"""

from src.invoice_service import _extract_why_factors

VENDOR_LIFT = {
    "type": "relatedPropositionLift", "value": 4.8,
    "proposition": {"vendor_business_id": "0787088-5"},
    "prior": {"type": "linkedPrior", "factors": [
        {"proposition": {"vendor_business_id.industry": {"$has": "Computer programming activities"}},
         "value": 4.162655958852747},
        {"proposition": {"vendor_business_id.industry_code": {"$has": "62100"}}, "value": 4.087348826317554},
    ]},
}

APPROVER_LIFT = {
    "type": "relatedPropositionLift", "value": 6.2,
    "proposition": {"$and": [{"vendor_business_id": "0787088-5"}, {"vendor": "Lapro Software Oy"}]},
    "prior": {"type": "linkedPrior", "factors": [
        {"proposition": {"department": "Procurement"}, "value": 4.345819546312811},
        {"proposition": {"role": "Manager"}, "value": 1.8785436815316856},
    ]},
}

CUSTOMER_FACT_LIFT = {
    "type": "relatedPropositionLift", "value": 2.5,
    "proposition": {"vendor": "Lapro Software Oy"},
    "prior": {"type": "linkedPrior", "factors": [
        {"proposition": {"customer_id.employee_count": {"$has": 160}}, "value": 7.98},
        {"proposition": {"vendor_business_id.industry": {"$has": "Computer programming activities"}}, "value": 4.2},
    ]},
}


def why(*lifts):
    return {"type": "product", "factors": [
        {"type": "baseP", "value": 0.12, "proposition": {"gl_code": {"$has": "6100"}}}, *lifts]}


def patterns(tree):
    return [f for f in _extract_why_factors(tree) if f["type"] == "pattern"]


def test_an_input_side_prior_names_what_the_vendor_is():
    (vendor,) = patterns(why(VENDOR_LIFT))
    assert vendor["priors"][0] == {"field": "vendor_business_id.industry",
                                   "value": "Computer programming activities", "lift": 4.163}


def test_a_target_side_prior_names_what_the_predicted_person_is():
    (approver,) = patterns(why(APPROVER_LIFT))
    assert [(p["field"], p["value"]) for p in approver["priors"]] == [("department", "Procurement"),
                                                                      ("role", "Manager")]


def test_customer_fact_priors_are_not_given_as_reasons():
    # customer_id.* priors come from the cross-tenant leak (ADR 0030).
    (pattern,) = patterns(why(CUSTOMER_FACT_LIFT))
    assert [p["field"] for p in pattern["priors"]] == ["vendor_business_id.industry"]


def test_a_lift_without_a_prior_has_an_empty_list_not_a_missing_key():
    plain = {"type": "relatedPropositionLift", "value": 3.0, "proposition": {"category": "software"}}
    (pattern,) = patterns(why(plain))
    assert pattern["priors"] == []
