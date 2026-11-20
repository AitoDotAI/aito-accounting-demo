"""What each tenant's own history says about a shared vendor.

The home page puts one vendor in front of several tenants and shows that
each routes it differently. Every answer here is an Aito `_predict` for
that tenant and vendor, so it comes with a probability and the `$why`
that explains it: the same vendor, the same query, only `customer_id`
differs.
"""

from src.aito_client import AitoClient
from src.formfill_service import predict_fields

# The fields the home page shows, in display order.
ROUTING_FIELDS = ("gl_code", "approver", "cost_centre")


def predict_vendor_routing(client: AitoClient, customer_id: str, vendor: str) -> dict | None:
    """Predict GL account, approver and cost centre for `vendor` in one tenant.

    Each field is `{value, display, p, why}` for Aito's top answer, plus the
    runners-up under `alternatives` for the GL account. Returns None when
    Aito has no answer above its noise floor for the GL account: the tenant
    has too little history with this vendor, and a guess would be invented.
    """
    # The Form Fill path already scopes the approver candidates to the
    # tenant's staff and names them; the home page asks the same question.
    predicted = predict_fields(client, {"customer_id": customer_id, "vendor": vendor}, only=ROUTING_FIELDS)
    by_field = {f["field"]: f for f in predicted["fields"]}

    routing: dict = {"vendor": vendor, "customer_id": customer_id}
    for field in ROUTING_FIELDS:
        alternatives = by_field[field]["alternatives"]
        if not alternatives:
            routing[field] = None
            continue
        top = alternatives[0]
        routing[field] = {
            "value": top["value"],
            "display": top["display"],
            "p": top["confidence"],
            "why": top["why"],
        }
    if routing["gl_code"] is None:
        return None
    routing["gl_code"]["alternatives"] = by_field["gl_code"]["alternatives"][1:]
    return routing
