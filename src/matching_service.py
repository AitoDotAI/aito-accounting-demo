"""Payment matching service — invoice to bank transaction pairing.

Uses Aito _predict on bank_transactions.invoice_id to find matching
invoices. Because invoice_id links to the invoices table, _predict
returns full invoice rows ranked by how well they associate with the
bank transaction's description and amount. The best match among open
invoices is selected by combining Aito's probability with amount
proximity.
"""

from dataclasses import dataclass, field

from src.aito_client import AitoClient, AitoError
from src.invoice_service import _extract_why_factors
from src.reference_lookup import find_invoice_by_reference, quotes_reference


@dataclass
class MatchPair:
    invoice_id: str
    invoice_vendor: str
    invoice_amount: float
    bank_txn_id: str | None
    bank_description: str | None
    bank_amount: float | None
    bank_name: str | None
    confidence: float
    status: str  # "matched", "suggested", "unmatched"
    # "reference" when the bank line quoted the invoice's reference and
    # no prediction was made; "aito" when `_predict` chose the invoice.
    matched_by: str | None = None
    explanation: list[dict] = field(default_factory=list)
    # Set when this pairing is a same-vendor SUBSTITUTE: the invoice Aito
    # actually ranked. The expanded row's explanation has to say so, and
    # it is deliberately NOT in `to_dict` -- it is how the match was made,
    # not something the page renders.
    ranked_invoice_id: str | None = None
    # Aito's own $p for this invoice, distinct from `confidence`, which
    # blends it with amount proximity. The panel needs both: the factor
    # chain is a decomposition of THIS number, not of the blend.
    model_p: float = 0.0

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "invoice_vendor": self.invoice_vendor,
            "invoice_amount": self.invoice_amount,
            "bank_txn_id": self.bank_txn_id,
            "bank_description": self.bank_description,
            "bank_amount": self.bank_amount,
            "bank_name": self.bank_name,
            "confidence": round(self.confidence, 2),
            "model_p": self.model_p,
            "status": self.status,
            "matched_by": self.matched_by,
            "explanation": self.explanation,
        }


def _amount_match_score(invoice_amount: float, bank_amount: float) -> float:
    """Score how close two amounts are. Returns 1.0 for exact, tapering to 0."""
    if invoice_amount == 0:
        return 0.0
    diff_pct = abs(invoice_amount - bank_amount) / invoice_amount
    if diff_pct == 0:
        return 1.0
    if diff_pct <= 0.005:
        return 0.95
    if diff_pct <= 0.02:
        return 0.80
    if diff_pct <= 0.05:
        return 0.50
    return 0.0


# The explanation's own select. `highlight` returns the matched description
# tokens already wrapped in <mark> tags -- Aito's text analyzer marks
# whichever spans of the bank description carried the signal.
WHY_SELECT = {"$why": {"highlight": {"posPreTag": "<mark>", "posPostTag": "</mark>"}}}


def ranking_query(txn: dict, open_ids: set[str], explain: bool = False) -> dict:
    """The question both paths ask: which open invoice settles this payment?

    One builder, because `$why` decomposes `$p` *within a candidate
    domain*. An explanation fetched under a different `where` would be a
    correct answer to a question the page never asked, and would not
    reconcile with the probability on screen. `explain=True` adds the
    explanation to the same request and changes nothing else.

    _predict invoice_id traverses the link and returns invoice rows ranked
    by association with the bank transaction's features.

    `customer_id` in `where` is EVIDENCE about the transaction; it does not
    restrict which invoices Aito may rank. Without the linked-path scope the
    candidate universe is every invoice in the instance, so a CUST-0002
    payment gets ranked against CUST-0000's invoices -- measured at 17
    foreign candidates in the top 5 over 8 payments. `invoice_id.customer_id`
    scopes the candidate domain through the link instead, which is the
    tenant boundary this page needs. It also happens to cut latency ~6x and
    the probability's under-confidence ~48x, but the boundary is the reason.

    `vendor_name` rides on the bank transaction and was not being passed.
    Four of five wrong assignments in a 640-invoice evaluation picked an
    invoice from the WRONG VENDOR while the description named the right
    one, so the field the bank already gives us was the missing evidence.

    The candidate domain is the OPEN LEDGER, not the whole invoice table.
    The question this page asks is "which outstanding invoice does this
    payment settle?" -- roughly 30 candidates. Without that clause Aito
    ranks all ~2000 of the tenant's invoices and we filter to the open
    ones afterwards, so the true invoice has to beat 1970 rows that were
    never eligible. It frequently does not: a payment quoting no
    reference number left CUST-0007-INV-000006 out of the top 20
    entirely, and the matcher settled on a different vendor at p=0.023.
    Scoped to the ledger the same payment ranks it FIRST at p=0.482.

    Use the linked key `invoice_id.invoice_id`, not the bare target
    `invoice_id`. Both rank correctly, but `$or` on the predict target
    itself returns `invoice_id: null` on every hit after the first --
    the matcher reads that field, so it would silently drop candidates.
    """
    where = {"description": txn["description"], "amount": txn["amount"]}
    customer_id = txn.get("customer_id")
    if customer_id is not None:
        where["customer_id"] = customer_id
        where["invoice_id.customer_id"] = customer_id
    if txn.get("vendor_name"):
        where["vendor_name"] = txn["vendor_name"]
    if open_ids:
        where["invoice_id.invoice_id"] = {"$or": sorted(open_ids)}

    select: list = ["$p", "invoice_id", "vendor", "amount"]
    if explain:
        select.append(WHY_SELECT)

    return {
        "from": "bank_transactions",
        "where": where,
        "predict": "invoice_id",
        "select": select,
        # Every open invoice, because the candidate domain is the ledger
        # itself. A fixed cut here is what truncated the true invoice out
        # of the ranking when the domain was all 2000.
        "limit": max(len(open_ids), 1),
    }


def match_bank_txn_to_invoice(
    client: AitoClient,
    txn: dict,
    open_invoices: list[dict],
    explain: bool = False,
) -> MatchPair | None:
    """Use Aito _predict invoice_id to match bank transaction to invoice.

    The bank_transactions.invoice_id links to invoices, so _predict
    returns full invoice rows from the linked table, ranked by how
    well they associate with the bank transaction's description and
    amount. We then pick the best match among open invoices.

    Single Aito query — no separate vendor resolution step needed.
    """
    open_ids = {inv["invoice_id"] for inv in open_invoices}
    open_by_id = {inv["invoice_id"]: inv for inv in open_invoices}
    open_by_vendor = {}
    for inv in open_invoices:
        open_by_vendor.setdefault(inv["vendor"], []).append(inv)

    try:
        result = client._request(
            "POST", "/_predict", json=ranking_query(txn, open_ids, explain=explain))
    except AitoError:
        return None

    # Direct hits and same-vendor substitutes are scored SEPARATELY, and a
    # direct hit always wins.
    #
    # They used to compete on one number, with the substitute weighting
    # amount 0.6 against a direct hit's 0.5. Because Aito's $p for a link
    # target is ~1e-3 while an amount score is ~1, the amount term decided
    # everything -- and a substitute from the wrong vendor with a marginally
    # closer amount beat the invoice Aito had ranked FIRST:
    #
    #   direct    INV-000146 Pukaron   0.00116*0.5 + 0.95*0.5 = 0.4756
    #   substitute INV-000171 Kardex   0.00015*0.4 + 0.95*0.6 = 0.5701  won
    #
    # Aito was right and the arithmetic threw it away. A substitute is a
    # fallback for when Aito ranked nothing we hold, never an improvement
    # on something it did.
    best_direct: tuple[float, dict, float, dict | None] | None = None
    best_sub: tuple[float, dict, float, str] | None = None

    for hit in result.get("hits", []):
        inv_id = hit.get("invoice_id")
        vendor = hit.get("vendor")
        aito_p = hit.get("$p", 0)

        # Direct match: Aito returned an open invoice.
        if inv_id in open_ids:
            amt_score = _amount_match_score(open_by_id[inv_id]["amount"], txn["amount"])
            combined = aito_p * 0.5 + amt_score * 0.5
            if best_direct is None or combined > best_direct[0]:
                best_direct = (combined, open_by_id[inv_id], aito_p, hit.get("$why"))
            continue

        # Indirect: Aito ranked a different invoice from the same vendor, so
        # we substitute an open one from that vendor whose amount fits.
        #
        # Aito's `$why` explains the invoice Aito ranked, NOT the one we
        # substitute, so it must not be carried over -- doing so rendered one
        # invoice's explanation under another invoice's match, with the base
        # rate naming an id that appeared nowhere on screen. `explain_match`
        # states the substitution instead, which is why the pair records
        # `ranked_invoice_id`.
        if vendor and vendor in open_by_vendor:
            for inv in open_by_vendor[vendor]:
                amt_score = _amount_match_score(inv["amount"], txn["amount"])
                combined = aito_p * 0.4 + amt_score * 0.6
                if best_sub is None or combined > best_sub[0]:
                    best_sub = (combined, inv, aito_p, inv_id)

    best_ranked_id: str | None = None
    if best_direct is not None:
        best_score, best_invoice, best_p, best_why = best_direct
    elif best_sub is not None:
        best_score, best_invoice, best_p, best_ranked_id = best_sub
        best_why = None
    else:
        best_score, best_invoice, best_p, best_why = 0.0, None, 0.0, None

    if best_invoice is None:
        return None

    # Classify confidence
    # _predict vendor_name gives higher $p values than _match, so
    # thresholds can be more meaningful.
    if best_score >= 0.30:
        status = "matched"
    elif best_score >= 0.15:
        status = "suggested"
    else:
        return None

    # The live list ships no explanation: it costs a $why for every
    # candidate to render one row, and `explain_match` fetches it for the
    # row the user expands (td-20260909115133919692). A precompute is built
    # once and served for days, so it takes the cost up front (`explain`)
    # and its rows never have to ask.
    explanation = (_build_explanation(txn, best_invoice, best_p, best_why, best_ranked_id)
                   if explain else [])
    return MatchPair(
        invoice_id=best_invoice["invoice_id"],
        invoice_vendor=best_invoice["vendor"],
        invoice_amount=best_invoice["amount"],
        bank_txn_id=txn["txn_id"],
        bank_description=txn["description"],
        bank_amount=txn["amount"],
        bank_name=txn["bank"],
        confidence=best_score,
        model_p=best_p,
        status=status,
        matched_by="aito",
        explanation=explanation,
        ranked_invoice_id=best_ranked_id,
    )


def explain_match(
    client: AitoClient,
    txn: dict,
    open_invoices: list[dict],
    invoice_id: str,
    ranked_invoice_id: str | None = None,
    model_p: float = 0.0,
    expected_invoice_id: str | None = None,
) -> list[dict]:
    """Explain one pairing: the row the user expanded, and only that row.

    Re-issues the ranking with `$why` added -- the same `where`, the same
    limit, the same candidate domain -- and reads the explanation of the
    invoice WE chose out of that ranking. Asking about the invoice on its
    own would decompose a different `$p` than the one on screen.

    A same-vendor substitute is not in Aito's ranking at all, so there is
    no `$why` to read for it and `_build_explanation` states the
    substitution instead. If the chosen invoice turns up in the ranking
    while the caller says it was substituted, the two disagree -- the data
    moved under a cached pairing -- and that is raised rather than
    rendered, because the alternative is a panel that explains one invoice
    and labels it another.

    `expected_invoice_id` is the invoice the caller is displaying. The
    pairing this explains is recomputed live when no explain context is
    cached -- which is every time the page was served from a precompute --
    so it can disagree with the row on screen if the ledger moved in
    between. Checked before the query, since the answer would be thrown
    away.
    """
    if expected_invoice_id is not None and expected_invoice_id != invoice_id:
        raise ValueError(
            f"the row shows invoice {expected_invoice_id} but this pairing "
            f"chose {invoice_id}: the ledger moved since the row was "
            f"rendered, so there is no explanation for what is on screen"
        )

    invoice = next((inv for inv in open_invoices if inv["invoice_id"] == invoice_id), None)
    if invoice is None:
        raise ValueError(
            f"{invoice_id} is not in the ledger this payment was matched against")

    open_ids = {inv["invoice_id"] for inv in open_invoices}
    try:
        result = client._request(
            "POST", "/_predict", json=ranking_query(txn, open_ids, explain=True))
    except AitoError:
        # The pairing stands -- it was made from a ranking that succeeded.
        # Only its explanation is missing, so say what we know without it.
        return _build_explanation(txn, invoice, model_p, None, ranked_invoice_id)

    why = next((hit.get("$why") for hit in result.get("hits", [])
                if hit.get("invoice_id") == invoice_id), None)
    if ranked_invoice_id is not None and why is not None:
        raise ValueError(
            f"{invoice_id} was recorded as a substitute for {ranked_invoice_id}, "
            "but Aito now ranks it directly -- the ranking changed under the pairing")

    return _build_explanation(txn, invoice, model_p, why, ranked_invoice_id)


def _build_explanation(
    txn: dict,
    invoice: dict,
    aito_p: float,
    aito_why: dict | None = None,
    ranked_invoice_id: str | None = None,
) -> list[dict]:
    """Pass through Aito $why factors in the grouped shape so the
    matching page can render the same WhyCards UI as Invoice
    Processing -- pattern cards with text-token highlights and lift
    multipliers.

    On top of that we append a synthetic "amount" factor only when the
    txn and invoice amounts disagree by >= 5% (worth flagging as a
    warning); exact/near-exact amounts would double-count Aito's own
    $why on the amount field.

    `ranked_invoice_id` is set when this match is a same-vendor
    SUBSTITUTE: Aito ranked that invoice, we are pairing a different one
    because its amount fits better. There is no Aito `$why` for the
    invoice we chose, so we state the substitution rather than borrowing
    the explanation of the invoice Aito did rank — which is a different
    invoice, and reads as gibberish under this one.
    """
    factors: list[dict] = list(_extract_why_factors(aito_why)) if aito_why else []

    if ranked_invoice_id is not None:
        factors.append({
            "type": "pattern",
            "lift": 1.0,
            "propositions": [
                {"field": "vendor", "value": invoice["vendor"]},
                {"field": "matched via", "value":
                    f"same vendor — Aito ranked {ranked_invoice_id}, "
                    f"this invoice's amount fits the payment better"},
            ],
            "highlights": [],
        })

    # Big-disagreement warning. Modelled as a pattern card with a
    # single proposition and lift = 1.0 noted in propositions[0].value
    # so the renderer can display it consistently.
    diff = abs(invoice["amount"] - txn["amount"])
    if invoice["amount"] > 0 and diff >= invoice["amount"] * 0.05:
        factors.append({
            "type": "pattern",
            "lift": 0.5,  # negative-signal flag: cuts confidence
            "propositions": [{"field": "amount", "value": f"differs by {diff:.2f}"}],
            "highlights": [],
        })

    return factors


def match_reference_first(
    client: AitoClient, txn: dict, open_invoices: list[dict], explain: bool = False
) -> MatchPair | None:
    """Match a payment by its quoted reference, or ask Aito if it quotes none.

    A reference on the bank line names the invoice outright, so reading
    it is the answer and not evidence to weigh. Only a payment without
    one -- or quoting one that matches no open invoice -- needs a
    prediction (ADR 0026).
    """
    invoice = find_invoice_by_reference(txn["description"], open_invoices)
    if invoice is None:
        return match_bank_txn_to_invoice(client, txn, open_invoices, explain=explain)
    return MatchPair(
        invoice_id=invoice["invoice_id"],
        invoice_vendor=invoice["vendor"],
        invoice_amount=invoice["amount"],
        bank_txn_id=txn["txn_id"],
        bank_description=txn["description"],
        bank_amount=txn["amount"],
        bank_name=txn["bank"],
        confidence=1.0,
        status="matched",
        matched_by="reference",
    )


def choose_payments_to_show(
    payments: list[dict],
    invoices_by_id: dict[str, dict],
    unreferenced: int,
    referenced: int,
) -> list[dict]:
    """Payments without a reference first, then a few that quote one.

    The unreferenced ones are the work an AP clerk actually does and the
    case Aito is here for; the referenced ones show that the lookup is
    handled too. Reads each payment's own invoice through the fixture's
    ground-truth link, which only decides what to DISPLAY.
    """
    def quotes_own_reference(payment: dict) -> bool:
        return quotes_reference(payment["description"], invoices_by_id[payment["invoice_id"]]["reference"])

    without = [p for p in payments if not quotes_own_reference(p)]
    with_reference = [p for p in payments if quotes_own_reference(p)]
    return without[:unreferenced] + with_reference[:referenced]


def match_all(
    client: AitoClient,
    customer_id: str | None = None,
    unreferenced_count: int = 6,
    referenced_count: int = 2,
    payment_window: int = 40,
    ledger_decoys: int = 30,
    include_explain_contexts: bool = False,
    inline_explanations: bool = False,
) -> dict:
    """Assign each incoming payment to an invoice in the open ledger.

    The direction matters and used to be backwards. A payment arrives and
    has to be assigned to an invoice; an invoice with no payment is simply
    unpaid, which is not a failure. Previously this fetched some payments
    and some *unrelated* invoices, matched what it could, and then listed
    every leftover invoice as "unmatched" — so a working matcher reported
    "5 matched, 15 unmatched" and read as 25% accurate. Those 15 invoices
    were never anyone's payment target; their payments had not been
    fetched at all.

    Now the ledger is built to contain the fetched payments' own invoices
    plus decoys, and only payments can be unmatched.

    Building the ledger uses `bank_transactions.invoice_id`, the fixture's
    ground-truth link, purely to decide WHICH invoices are outstanding —
    a real deployment reads that from its AP ledger instead. The matcher
    itself never sees the link: it gets `description` and `amount` only,
    and has to re-derive the pairing.

    Which payments are shown is chosen from a wider window so that most of
    them quote no reference (ADR 0026). The first eight of the table are
    typically 5-7 referenced payments, whose answer is printed on the
    bank line.

    `include_explain_contexts` adds what `explain_match` needs to answer
    "why this invoice?" later: the payment, and the open ledger as it
    stood when that payment was ranked. The ledger shrinks as payments
    are assigned, so it cannot be reconstructed from the result -- and
    without the same ledger the explanation would decompose a different
    probability. It is off by default because it belongs to the request
    that served the page, not in a precompute file or an audit report.

    `inline_explanations` is the precompute's way: every Aito-matched pair
    carries its own explanation, so a page served from the file never has
    to rebuild the pairing live to answer "why?".
    """
    try:
        where = {"customer_id": customer_id} if customer_id else {}
        window = client.search("bank_transactions", where, limit=payment_window).get("hits", [])
        if not window:
            raise AitoError("no bank transactions for this customer")

        window_invoice_ids = sorted({t["invoice_id"] for t in window})
        window_invoices = {
            row["invoice_id"]: row
            for row in client.search(
                "invoices", {**where, "invoice_id": {"$or": window_invoice_ids}},
                limit=len(window_invoice_ids),
            ).get("hits", [])
        }
        missing = set(window_invoice_ids) - set(window_invoices)
        if missing:
            raise AitoError(f"bank transactions link to invoices Aito did not return: {sorted(missing)}")

        payments = choose_payments_to_show(window, window_invoices, unreferenced_count, referenced_count)
        # The invoices these payments settle — the ledger must contain
        # them, or the task is unanswerable rather than hard.
        target_rows = [window_invoices[t["invoice_id"]] for t in payments]

        # Decoys, so choosing the right invoice is a real discrimination.
        decoy_rows = client.search("invoices", where, limit=ledger_decoys).get("hits", [])
    except AitoError:
        return {"pairs": [], "metrics": {"matched": 0, "suggested": 0, "unmatched": 0,
                                         "matched_by_reference": 0, "matched_by_aito": 0,
                                         "total": 0, "avg_confidence": 0, "match_rate": 0}}

    ledger: dict[str, dict] = {}
    for row in target_rows + decoy_rows:
        ledger.setdefault(row["invoice_id"], {
            "invoice_id": row["invoice_id"],
            "vendor": row["vendor"],
            "amount": row["amount"],
            "reference": row["reference"],
        })

    bank_txns = [{
        "txn_id": t.get("transaction_id"),
        "description": t["description"],
        "amount": t["amount"],
        "bank": t.get("bank", ""),
        "customer_id": customer_id,
        # Carried, or `match_bank_txn_to_invoice` reads None and silently
        # drops the vendor evidence it is written to use. Without it the
        # true invoice falls out of Aito's top 20 entirely -- measured on
        # CUST-0000-INV-000011: rank 1 with vendor_name, not ranked at all
        # without -- and the matcher then substitutes a same-vendor invoice
        # and explains itself with "Aito ranked <some other invoice>".
        "vendor_name": t.get("vendor_name"),
    } for t in payments]

    pairs: list[MatchPair] = []
    explain_contexts: dict[str, dict] = {}
    remaining = list(ledger.values())
    for txn in bank_txns:
        # The ledger as this payment saw it, before its invoice is taken
        # out of circulation: the candidate domain its $p was computed in.
        ledger_at_ranking = list(remaining)
        pair = match_reference_first(client, txn, remaining, explain=inline_explanations)
        if pair is not None:
            pairs.append(pair)
            if pair.matched_by == "aito":
                explain_contexts[txn["txn_id"]] = {
                    "txn": txn,
                    "open_invoices": ledger_at_ranking,
                    "invoice_id": pair.invoice_id,
                    "ranked_invoice_id": pair.ranked_invoice_id,
                    "model_p": pair.model_p,
                }
            # One invoice settles one payment.
            remaining = [inv for inv in remaining if inv["invoice_id"] != pair.invoice_id]
        else:
            pairs.append(MatchPair(
                invoice_id="", invoice_vendor="", invoice_amount=0.0,
                bank_txn_id=txn["txn_id"], bank_description=txn["description"],
                bank_amount=txn["amount"], bank_name=txn["bank"],
                confidence=0.0, status="unmatched",
            ))

    matched = sum(1 for p in pairs if p.status == "matched")
    suggested = sum(1 for p in pairs if p.status == "suggested")
    unmatched = sum(1 for p in pairs if p.status == "unmatched")
    # Averaged over Aito's matches only: a lookup's 1.0 is not a
    # confidence the model earned, and would inflate the figure.
    confidences = [p.confidence for p in pairs if p.matched_by == "aito"]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    result = {
        "pairs": [p.to_dict() for p in pairs],
        "metrics": {
            "matched": matched,
            "suggested": suggested,
            "unmatched": unmatched,
            "matched_by_reference": sum(1 for p in pairs if p.matched_by == "reference"),
            "matched_by_aito": sum(1 for p in pairs if p.matched_by == "aito"),
            "total": len(pairs),
            "ledger_size": len(ledger),
            "avg_confidence": round(avg_conf, 2),
            "match_rate": round((matched + suggested) / len(pairs), 2) if pairs else 0,
        },
    }
    if include_explain_contexts:
        result["explain_contexts"] = explain_contexts
    return result
