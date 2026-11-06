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


# ── The row and the explanation must be about the same invoice ──────
#
# /api/matching/pairs serves the precompute when there is one, and the
# precompute carries no explain contexts. So /explain finds an empty
# context cache, reruns match_all live, and explains whatever the LIVE
# pairing chose. If the data moved since the precompute was generated --
# a new invoice, a settled one, a re-run after ADR 0026 -- the live
# pairing can land on a different invoice than the row on screen, and
# the row then shows a decomposition of a different invoice's $p under
# its own heading. Exactly the defect
# TestExplanationBelongsToTheMatchedInvoice guards inside one
# computation, reappearing at the seam between two.
#
# The row knows which invoice it is showing, so it says so, and a
# disagreement is refused rather than rendered.


def test_explaining_a_different_invoice_than_the_row_shows_is_refused():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    try:
        explain_match(client, TXN, LEDGER, "INV-1", None, 0.9,
                      expected_invoice_id="INV-2")
    except ValueError as exc:
        assert "INV-1" in str(exc) and "INV-2" in str(exc)
    else:
        raise AssertionError("explained INV-1 under a row showing INV-2")


def test_the_disagreement_is_caught_before_the_query_is_spent():
    # The explanation costs a full ranking with $why over the whole
    # ledger. There is no reason to pay for one we are going to discard.
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    try:
        explain_match(client, TXN, LEDGER, "INV-1", None, 0.9,
                      expected_invoice_id="INV-2")
    except ValueError:
        pass
    assert client.bodies == [], "asked Aito before checking the row agreed"


def test_an_agreeing_row_is_explained_as_before():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    factors = explain_match(client, TXN, LEDGER, "INV-1", None, 0.9,
                            expected_invoice_id="INV-1")
    assert factors, "the agreeing case must still explain"


def test_a_row_that_states_no_invoice_is_still_explained():
    # Back-compatible on purpose: the guard is for a row that names a
    # DIFFERENT invoice, not for one that names none.
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    assert explain_match(client, TXN, LEDGER, "INV-1", None, 0.9)


# ── The precompute path keeps its explanations ─────────────────────────
#
# On demand is for the LIVE page. A precompute is built once, offline, and
# served for days; if it carried no explanations every expanded row would
# rebuild the pairing live (14 s cold) and could disagree with the file.
# CPO review of #65, 2026-11-05.

def test_the_precompute_path_ships_the_explanation_inline():
    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    pair = match_bank_txn_to_invoice(client, TXN, LEDGER, explain=True)

    assert has_why(client.selects[0]), "the precompute ranking did not ask for $why"
    base = next(f for f in pair.explanation if f["type"] == "base")
    assert base["target_value"] == "INV-1"


def test_an_inline_substitute_states_the_substitution_not_the_ranked_invoices_why():
    client = RecordingClient([
        {"invoice_id": "INV-9", "vendor": "ACME Oy", "amount": 250.0,
         "$p": 0.4, "$why": why_for("INV-9")},
    ])
    pair = match_bank_txn_to_invoice(client, TXN, LEDGER, explain=True)

    assert pair.invoice_id == "INV-1"
    assert "INV-9" not in [f.get("target_value") for f in pair.explanation if f["type"] == "base"]
    rendered = " ".join(p["value"] for f in pair.explanation for p in f.get("propositions", []))
    assert "same vendor" in rendered


def test_the_precompute_script_asks_for_inline_explanations(monkeypatch):
    import importlib

    module = importlib.import_module("data.precompute_predictions")
    seen = {}
    monkeypatch.setattr(module, "match_all",
                        lambda client, **kwargs: seen.update(kwargs) or {})
    module.precompute_matching(object(), "CUST-0000")

    assert seen.get("inline_explanations") is True


class LedgerClient(RecordingClient):
    """One payment for INV-1 against a two-invoice ledger, as match_all reads it."""

    def search(self, table, where, limit=10):
        if table == "bank_transactions":
            return {"hits": [{"transaction_id": "T-1", "invoice_id": "INV-1",
                              "description": TXN["description"], "amount": 1000.0,
                              "bank": "Nordea", "vendor_name": "ACME Oy"}]}
        return {"hits": [{**inv, "reference": "REF-" + inv["invoice_id"]} for inv in LEDGER]}


def test_match_all_inlines_explanations_only_when_asked():
    from src.matching_service import match_all

    hits = [{"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
             "$p": 0.9, "$why": why_for("INV-1")}]

    live = LedgerClient(hits)
    live_result = match_all(live, customer_id="CUST-0000")
    inline = LedgerClient(hits)
    inline_result = match_all(inline, customer_id="CUST-0000", inline_explanations=True)

    assert not has_why(live.selects[0]) and live_result["pairs"][0]["explanation"] == []
    assert has_why(inline.selects[0]) and inline_result["pairs"][0]["explanation"]


# ── A substitute that Aito now ranks directly ───────────────────────────

def test_a_recorded_substitute_that_aito_now_ranks_is_refused_not_explained():
    # The pairing recorded INV-1 as a substitute for INV-9. If Aito now ranks
    # INV-1 itself, the data moved: explaining it with its own $why would
    # contradict the "substitute" the row was labelled with. Mutating the
    # guard to False must break this test.
    import pytest

    client = RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0,
         "$p": 0.9, "$why": why_for("INV-1")},
    ])
    with pytest.raises(ValueError, match="ranking changed"):
        explain_match(client, TXN, LEDGER, "INV-1", ranked_invoice_id="INV-9", model_p=0.4)


def test_a_pair_says_whether_it_is_a_substitute_without_an_explanation():
    # The live list carries no explanation, so the page cannot read this off it.
    direct = match_bank_txn_to_invoice(RecordingClient([
        {"invoice_id": "INV-1", "vendor": "ACME Oy", "amount": 1000.0, "$p": 0.9}]), TXN, LEDGER)
    substitute = match_bank_txn_to_invoice(RecordingClient([
        {"invoice_id": "INV-9", "vendor": "ACME Oy", "amount": 250.0, "$p": 0.4}]), TXN, LEDGER)

    assert direct.explanation == [] and substitute.explanation == []
    assert direct.to_dict()["substituted"] is False
    assert substitute.to_dict()["substituted"] is True
