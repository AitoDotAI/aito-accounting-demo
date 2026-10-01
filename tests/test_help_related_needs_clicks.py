"""'Users who read this also read' lists only articles someone actually read next.

`_recommend` on a link target can rank a candidate with no supporting clicks
first, at $p of about 0.998 (engine issue td-20261001174213737932). The
drawer's heading claims users read these articles next, so each candidate
carries the number of times this customer's users opened it right after the
current article, and the drawer lists only those with at least one.
"""

from src.help_service import related_articles

TENANT = "CUST-0000"


class Recording:
    def __init__(self, clicks_by_article):
        self.clicks_by_article = clicks_by_article
        self.counts = []

    def recommend(self, table, where, field, **kw):
        return {"hits": [{"article_id": a, "$p": 0.9} for a in ("APP-02", "APP-06", "LEGAL-07")]}

    def search(self, table, where, limit=10):
        self.counts.append((table, where, limit))
        return {"total": self.clicks_by_article[where["article_id"]], "hits": []}


def test_each_related_article_carries_its_supporting_clicks():
    client = Recording({"APP-06": 3, "LEGAL-07": 0})
    out = related_articles(client, "APP-02", TENANT)
    assert [(a["article_id"], a["supporting_clicks"]) for a in out] == [("APP-06", 3), ("LEGAL-07", 0)]


def test_supporting_clicks_are_this_customers_clicks_from_the_current_article():
    client = Recording({"APP-06": 3, "LEGAL-07": 0})
    related_articles(client, "APP-02", TENANT)
    assert ("help_impressions",
            {"customer_id": TENANT, "prev_article_id": "APP-02", "article_id": "APP-06", "clicked": True},
            0) in client.counts
