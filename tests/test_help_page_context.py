"""The help drawer's page context must match what impressions recorded.

The production build uses Next's `trailingSlash: true`, so the drawer
sends `/invoices/`, while every recorded impression says `/invoices`. The
page evidence then matched nothing and the ranking fell back to generic
popularity: on Tornio's Invoices page the drawer showed APP-00..04 instead
of Tornio's own "Approval policy: invoices over EUR 10,000" and "Cost
centre rules" -- which rank first and second with `/invoices`.
"""

from src.help_service import log_impression, normalize_page, search_help


class Recording:
    def __init__(self):
        self.recommend_where = None
        self.inserted = []

    def recommend(self, table, where, field, **kw):
        self.recommend_where = where
        return {"hits": []}

    def _request(self, method, path, json=None, timeout=None):
        self.inserted.append(json)
        return {}

    def insert_batch(self, name, rows, batch_size=1000):
        self.inserted.extend(rows)
        return len(rows)


def test_a_trailing_slash_is_dropped():
    assert normalize_page("/invoices/") == "/invoices"
    assert normalize_page("/quality/overview/") == "/quality/overview"


def test_root_and_empty_are_left_alone():
    assert normalize_page("/") == "/"
    assert normalize_page("") == ""


def test_search_uses_the_recorded_form():
    c = Recording()

    search_help(c, "CUST-0000", page="/invoices/")

    assert c.recommend_where["page"] == "/invoices"


def test_impressions_are_recorded_in_the_same_form():
    """Otherwise the live site keeps writing `/invoices/` impressions that
    the next search cannot learn from."""
    c = Recording()

    log_impression(c, "APP-01", "CUST-0000", page="/invoices/", clicked=True)

    rows = [r for r in c.inserted if isinstance(r, dict)] + [
        r for batch in c.inserted if isinstance(batch, list) for r in batch]
    assert any(r.get("page") == "/invoices" for r in rows), c.inserted
