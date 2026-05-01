"""Help system: contextual ranking via Aito _recommend.

Three article categories: app (product docs), legal (compliance
pointers), internal (per-customer guidance).

Ranking strategy: a single Aito `_recommend` call. Same operator,
same goal-driven CTR ranking that aito-demo uses for product
recommendations:

    POST /_recommend
      from:      help_impressions
      where:
        customer_id:               <current>
        page:                      <current page>     # context
        article_id.customer_id:    {"$or": ["*", current]}   # eligibility
        $or:                                                  # query honesty
          - { article_id.title: {"$match": query} }
          - { article_id.body:  {"$match": query} }
      recommend: article_id        # link to help_articles
      goal:      {clicked: true}   # optimise for clicks
      select:    [$p, article_id, title, body, category, tags,
                  page_context, customer_id]

Two things make the single-call shape work:

1. `recommend: article_id` is a link field. The `select` traverses
   the link automatically — title/body/category come from the
   linked help_articles row, no second `_search` needed.

2. `where` keys can be dotted to reference linked-table fields.
   `article_id.customer_id` filters the candidate pool to the
   eligibility set (no client-side filter). `article_id.title:
   {"$match": q}` uses Aito's text analyzer (stemming, stopwords)
   to apply the user's query honestly.

Goal-driven ranking does the rest: `goal: {clicked: true}` ranks
the eligible candidates by predicted P(click) given the context.
New impressions become new training data; the next call
automatically reflects them, no retraining.

Logging: every shown article writes an impression row; every click
writes a second row with clicked=true. The signal is implicit in
the impression history.
"""

import time
import uuid

from src.aito_client import AitoClient, AitoError


def _eligibility_clause(customer_id: str) -> dict:
    """Articles this customer can see: global ('*') + own internal."""
    return {"$or": ["*", customer_id]}


def _query_clause(query: str) -> dict:
    """Aito-analyzer match across title and body so the result must
    actually contain the user's words. The analyzer does stemming and
    stopword removal — much better than a literal substring filter."""
    return {"$or": [
        {"article_id.title": {"$match": query}},
        {"article_id.body": {"$match": query}},
    ]}


def search_help(
    client: AitoClient,
    customer_id: str,
    page: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return click-through-ranked help articles for the current context.

    Single `_recommend` call: linked-field `select` returns the
    rendered article rows directly; linked-field `where` filters
    eligibility and applies the text query server-side. No catalog
    cache, no client-side post-filtering.
    """
    where: dict = {
        "customer_id": customer_id,
        "article_id.customer_id": _eligibility_clause(customer_id),
    }
    if page:
        where["page"] = page
    if query:
        where.update(_query_clause(query))

    try:
        result = client._request("POST", "/_recommend", json={
            "from": "help_impressions",
            "where": where,
            "recommend": "article_id",
            "goal": {"clicked": True},
            "select": [
                "$p", "article_id", "title", "body", "category",
                "tags", "page_context", "customer_id",
            ],
            "limit": limit,
        })
    except AitoError:
        return []

    return result.get("hits", [])[:limit]


def related_articles(
    client: AitoClient,
    article_id: str,
    customer_id: str,
    limit: int = 4,
) -> list[dict]:
    """Articles users tend to click next after viewing `article_id`.

    `_recommend` over `help_impressions` where the user's previous
    article was `article_id`. `prev_article_id` is itself a link to
    help_articles, but we filter on the link key directly — Aito's
    candidate filter is on `article_id.customer_id`, the link from
    impression to the *recommended* article.
    """
    where = {
        "prev_article_id": article_id,
        "customer_id": customer_id,
        "article_id.customer_id": _eligibility_clause(customer_id),
    }

    # Over-fetch by 1 so we can drop the source article if it self-recommends.
    # Aito's `recommend` field doesn't accept {"$not": ...} (link fields take
    # values, not comparison clauses), so the exclusion stays client-side.
    try:
        result = client._request("POST", "/_recommend", json={
            "from": "help_impressions",
            "where": where,
            "recommend": "article_id",
            "goal": {"clicked": True},
            "select": [
                "$p", "article_id", "title", "body", "category",
                "tags", "page_context", "customer_id",
            ],
            "limit": limit + 1,
        })
    except AitoError:
        return []

    out = []
    for hit in result.get("hits", []):
        if hit.get("article_id") == article_id:
            continue
        row = dict(hit)
        row["score"] = round(float(hit.get("$p", 0)), 3)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def customer_help_stats(client: AitoClient, customer_id: str) -> dict:
    """Per-customer impression / click / CTR rollup.

    Two `_search` calls with `limit: 0` return only the `total`
    field — cheaper than fetching rows. CTR (clicks ÷ impressions)
    is the single deflection number worth surfacing: above the
    typed-search baseline (which is closer to 1–3% for in-app help
    on category pages) it argues that context-aware ranking pulls
    the right article up far enough that users open it instead of
    typing into the support form.
    """
    def _count(where: dict) -> int:
        try:
            r = client._request("POST", "/_search", json={
                "from": "help_impressions",
                "where": where,
                "limit": 0,
            })
            return int(r.get("total", 0))
        except AitoError:
            return 0

    impressions = _count({"customer_id": customer_id})
    clicks = _count({"customer_id": customer_id, "clicked": True})
    ctr = (clicks / impressions) if impressions else 0.0
    return {
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(ctr, 4),
    }


def log_impression(
    client: AitoClient,
    article_id: str,
    customer_id: str,
    page: str,
    query: str = "",
    clicked: bool = False,
    prev_article_id: str | None = None,
) -> None:
    """Record that an article was shown (or clicked) for ranking.

    `prev_article_id`, if given, is the article the user was viewing
    immediately before this one — drives the related-articles
    ranking on subsequent calls.
    """
    row = {
        "impression_id": f"IMP-{uuid.uuid4().hex[:12]}",
        "article_id": article_id,
        "customer_id": customer_id,
        "page": page,
        "query": query,
        "clicked": clicked,
        "timestamp": int(time.time()),
        "prev_article_id": prev_article_id,
    }
    try:
        client._request("POST", "/data/help_impressions", json=row)
    except AitoError:
        pass  # best-effort
