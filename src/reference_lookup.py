"""Reference-number lookup — the part of payment matching that needs no model.

A Finnish supplier prints a reference on its invoice (`VIITE 468883814`,
or an ISO 11649 `RF18 1234 5678`), and the payer quotes it back. When the
bank line carries that reference, the matching invoice is found by
reading it. Every AP system does this before anything clever, and so does
this demo: only payments this lookup cannot resolve are sent to Aito
(see ADR 0026).

Banks reformat the reference freely — `Viite: 745074511`,
`ref=VIITE 468883814`, `RF18 1234 5678` split across spaces — so both
strings are compared as sequences of alphanumeric tokens. A reference
must appear as whole, consecutive tokens: `1234` inside the date
`12345678` is not a quote of reference `1234`.
"""

import re

_TOKEN = re.compile(r"[A-Z0-9]+")

# The word a Finnish bank puts in front of a domestic reference. It
# labels the number rather than being part of it, and banks spell it
# differently (`VIITE`, `Viite:`), so it is not required to match.
_REFERENCE_LABEL = "VIITE"


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.upper())


def reference_tokens(reference: str) -> list[str]:
    """The tokens a payer has to quote for `reference` to count as quoted."""
    tokens = [t for t in _tokens(reference) if t != _REFERENCE_LABEL]
    if not tokens:
        raise ValueError(f"invoice reference {reference!r} contains no reference number")
    return tokens


def quotes_reference(description: str, reference: str) -> bool:
    """True when the bank description quotes this invoice reference."""
    wanted = reference_tokens(reference)
    found = _tokens(description)
    return any(
        found[i:i + len(wanted)] == wanted
        for i in range(len(found) - len(wanted) + 1)
    )


def find_invoice_by_reference(description: str, open_invoices: list[dict]) -> dict | None:
    """The open invoice whose reference the payment quotes, if exactly one.

    Two open invoices can never legitimately share a reference, so a
    description that quotes two of them is a data error, not a tie to
    break.
    """
    quoted = [inv for inv in open_invoices if quotes_reference(description, inv["reference"])]
    if len(quoted) > 1:
        ids = ", ".join(inv["invoice_id"] for inv in quoted)
        raise ValueError(f"bank description {description!r} quotes the reference of several open invoices: {ids}")
    return quoted[0] if quoted else None
