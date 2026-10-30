"""Ranking asks which invoice; only the expanded row asks why (td-20260909115133919692).

Measured read-only on CUST-0000 against shared 2.11.9: the ranking
`_predict` selected `$why` with highlight for the whole open ledger -- 30
candidates, 30 explanations returned, exactly one used (the best direct
hit; the substitute path discards its `$why` by design). The response was
74.6 KiB with `$why` and 5.1 KiB without, so 93% of what the page
downloaded explained invoices nobody expanded, and the ranking is
identical without it. Latency is the smaller half: 789 ms against 683 ms
median over nine repeats, about 14%, with single runs from 603 to 1406 ms
either way.

The expanded row re-issues the SAME `where` and reads the chosen
invoice's `$why` out of that ranking. It must not ask about the invoice in
isolation: `$why` is a decomposition of `$p` within a candidate domain, so
a question with a different domain would answer about a different number.
"""

from src.matching_service import explain_match, match_bank_txn_to_invoice

TXN = {
    "txn_id": "CUST-0000-TXN-000001",
    "description": "ACME OY 15052025",
    "amount": 1000.0,
    "bank": "Nordea",
    "customer_id": "CUST-0000",
    "vendor_name": "ACME Oy",
}
LEDGER = [
    {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0},
    {"invoice_id": "INV-2", "vendor": "Bolt Oy", "amount": 400.0},
]


def why_for(invoice_id: str, lift: float = 8.0) -> dict:
    return {
        "type": "product",
        "factors": [
            {"type": "baseP", "value": 7.8e-06,
             "proposition": {"invoice_id": {"$has": invoice_id}}},
            {"type": "relatedPropositionLift", "value": lift,
             "proposition": {"description": {"$has": "ACME"}}},
        ],
    }


class RecordingClient:
    """Canned `_predict` answers, with every request body kept."""

    def __init__(self, hits):
        self._hits = hits
        self.bodies: list[dict] = []

    def _request(self, method, path, json=None, timeout=120.0):
        self.bodies.append(json)
        return {"hits": self._hits}

    @property
    def selects(self) -> list[list]:
        return [body["select"] for body in self.bodies]


def has_why(select: list) -> bool:
    return any(isinstance(item, dict) and "$why" in item for item in select)


def test_the_ranking_does_not_ask_for_why():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0, "$p": 0.9},
    ])
    match_bank_txn_to_invoice(client, TXN, LEDGER)
    assert client.selects, "the matcher asked Aito nothing"
    assert not has_why(client.selects[0]), \
        "the ranking still pays for an explanation of every candidate"


def test_a_matched_pair_ships_without_an_explanation():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0, "$p": 0.9},
    ])
    pair = match_bank_txn_to_invoice(client, TXN, LEDGER)
    assert pair.invoice_id == "INV-1"
    assert pair.explanation == [], "the list response carries explanations again"


def test_the_expanded_row_asks_the_same_question_with_why_added():
    # $why decomposes $p within a candidate domain. Asked with a
    # different where, it would explain a different number.
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    match_bank_txn_to_invoice(client, TXN, LEDGER)
    explain_match(client, TXN, LEDGER, "INV-1", model_p=0.9)

    ranking, explaining = client.bodies[0], client.bodies[1]
    assert explaining["where"] == ranking["where"]
    assert explaining["limit"] == ranking["limit"]
    assert explaining["predict"] == ranking["predict"]
    assert has_why(explaining["select"]), "the expanded row did not ask for $why"


def test_the_expanded_row_explains_the_invoice_we_chose():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    factors = explain_match(client, TXN, LEDGER, "INV-1", model_p=0.9)
    base = next(f for f in factors if f["type"] == "base")
    assert base["target_value"] == "INV-1"


def test_a_substituted_match_states_the_substitution_without_borrowing_a_why():
    # Aito ranks INV-9, which is not in the ledger; the matcher pairs
    # INV-1, same vendor, whose amount fits. The explanation of INV-9
    # describes a different invoice and must not appear under this one --
    # it reached a live demo once, naming an id nowhere on screen.
    client = RecordingClient([
        {"invoice_id": "INV-9", "vendor": "ACME Oy", "amount": 250.0,
         "$p": 0.4, "$why": why_for("INV-9")},
    ])
    pair = match_bank_txn_to_invoice(client, TXN, LEDGER)
    assert pair.invoice_id == "INV-1", "expected a same-vendor substitution"
    assert pair.ranked_invoice_id == "INV-9", \
        "the pair must carry what Aito ranked, or the explanation cannot say so"

    factors = explain_match(client, TXN, LEDGER, pair.invoice_id,
                            ranked_invoice_id=pair.ranked_invoice_id,
                            model_p=pair.model_p)
    assert "INV-9" not in [f.get("target_value") for f in factors if f["type"] == "base"]
    rendered = " ".join(p["value"] for f in factors for p in f.get("propositions", []))
    assert "INV-9" in rendered and "same vendor" in rendered


def test_the_explanation_costs_one_query():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    explain_match(client, TXN, LEDGER, "INV-1", model_p=0.9)
    assert len(client.bodies) == 1
