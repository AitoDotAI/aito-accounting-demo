"""Help system: contextual ranking via Aito _recommend.

Three article categories: app (product docs), legal (compliance
pointers), internal (per-customer guidance).

Ranking strategy: Aito's `_recommend` operator — the same one
aito-demo uses for product recommendations. The semantics fit
help articles exactly:

    POST /_recommend
      from:      help_impressions             # impression history
      where:     { customer_id, page, [query] }  # current context
      recommend: article_id                   # what to recommend
      goal:      { clicked: true }            # optimise for clicks

Aito returns article_ids ranked by the predicted probability of
the goal (a click) being achieved given the context — i.e. CTR-
ranked recommendations. New clicks become new impression rows;
the next call automatically reflects them, no retraining.

Logging: every shown article writes an impression row; every click
writes a second row with clicked=true. The signal is implicit in
the impression history.
"""

import time
import uuid

from src.aito_client import AitoClient, AitoError


def search_help(
    client: AitoClient,
    customer_id: str,
    page: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return click-through-ranked help articles for the current context.

    Two Aito calls:
      1. `_search` help_articles WHERE customer_id IN ("*", current)
         to fetch the eligible article pool (ids, titles, bodies for
         rendering, plus filtering set). Cached per customer for 1 h
         since the article catalogue is stable.
      2. `_recommend` against help_impressions for CTR ranking.

    On cold start (no impression history) the recommend pool is
    empty, and we top up with the eligible pool directly.

    `_recommend` cannot return linked help_articles fields via
    `select`, so we still need the search call to render titles
    and bodies. But we collapse the two old eligibility searches
    (one global, one per-customer) into a single `$or` query.
    """
    base_where: dict = {"customer_id": customer_id}
    if page:
        base_where["page"] = page
    if query:
        base_where["query"] = query

    # Single eligibility query: global articles + this customer's own.
    # Cached server-side; the catalog doesn't churn during a session.
    try:
        eligible = client.search(
            "help_articles",
            {"customer_id": {"$or": ["*", customer_id]}},
            limit=250,
        ).get("hits", [])
    except AitoError:
        return []
    by_id = {a["article_id"]: a for a in eligible}
    eligible_ids = set(by_id.keys())
    eligible_global = [a for a in eligible if a.get("customer_id") == "*"]
    eligible_own = [a for a in eligible if a.get("customer_id") == customer_id]

    # Aito _recommend returns ranked article_ids globally — its where
    # clause biases ranking but doesn't restrict the candidate pool.
    # Most high-$p hits are other-customer internal articles which we
    # filter out via the eligibility set. We over-fetch generously
    # then top up from the eligibility pool itself so the user always
    # gets `limit` articles even if _recommend's signal is sparse.
    try:
        result = client._request("POST", "/_recommend", json={
            "from": "help_impressions",
            "where": base_where,
            "recommend": "article_id",
            "goal": {"clicked": True},
            "limit": 100,
        })
    except AitoError:
        result = {"hits": []}

    ranked_ids: list[str] = []
    seen: set[str] = set()
    for hit in result.get("hits", []):
        aid = hit.get("article_id")
        if not aid or aid in seen or aid not in eligible_ids:
            continue
        seen.add(aid)
        ranked_ids.append(aid)

    # Top up to `limit` with eligible articles not yet ranked. When
    # the user typed a query, restrict topups (and post-filter the
    # ranked list) to articles whose title/body/tags actually contain
    # the query tokens. Otherwise q="GL code" and q="zzznoresults"
    # would return identical lists -- the fallback path was query-blind.
    def _match_query(article: dict) -> bool:
        if not query:
            return True
        haystack = " ".join([
            article.get("title", ""),
            article.get("body", ""),
            article.get("tags", ""),
            article.get("category", ""),
        ]).lower()
        # Every >=3-character token in the query must appear somewhere
        # in the article. Aito's analyzer would tokenize differently
        # (stemming, stopwords) but this is the visible filter the user
        # typed -- exact substring is honest.
        tokens = [t for t in query.lower().split() if len(t) >= 3]
        return all(t in haystack for t in tokens) if tokens else True

    if query:
        ranked_ids = [aid for aid in ranked_ids if aid in by_id and _match_query(by_id[aid])]

    if len(ranked_ids) < limit:
        own_match = [a["article_id"] for a in eligible_own if a.get("page_context") == page and page and _match_query(a)]
        own_other = [a["article_id"] for a in eligible_own if _match_query(a)]
        global_match = [a["article_id"] for a in eligible_global if a.get("page_context") == page and page and _match_query(a)]
        global_other = [a["article_id"] for a in eligible_global if _match_query(a)]
        for aid in own_match + own_other + global_match + global_other:
            if aid in seen:
                continue
            seen.add(aid)
            ranked_ids.append(aid)
            if len(ranked_ids) >= limit:
                break

    return [by_id[aid] for aid in ranked_ids[:limit] if aid in by_id]


def related_articles(
    client: AitoClient,
    article_id: str,
    customer_id: str,
    limit: int = 4,
) -> list[dict]:
    """Articles users tend to click next after viewing `article_id`.

    The signal: every impression carries `prev_article_id`. Aito's
    `_recommend WHERE prev_article_id = X, customer_id = Y, goal:
    {clicked: true}` ranks article_ids by predicted P(click) given
    that the user just clicked X. This is the standard "users who
    read this also read" pattern, modelled directly through Aito.

    Filtered to the customer's eligibility set (global "*" + own
    internal articles) and to exclude the source article itself.
    """
    # Single eligibility query (global + own) via $or.
    try:
        eligible = client.search(
            "help_articles",
            {"customer_id": {"$or": ["*", customer_id]}},
            limit=250,
        ).get("hits", [])
    except AitoError:
        return []
    by_id = {a["article_id"]: a for a in eligible}

    try:
        result = client._request("POST", "/_recommend", json={
            "from": "help_impressions",
            "where": {"prev_article_id": article_id, "customer_id": customer_id},
            "recommend": "article_id",
            "goal": {"clicked": True},
            "limit": limit * 5,  # over-fetch to allow filtering
        })
    except AitoError:
        result = {"hits": []}

    out = []
    for hit in result.get("hits", []):
        aid = hit.get("article_id")
        if not aid or aid == article_id:
            continue
        if aid not in by_id:
            continue
        art = dict(by_id[aid])
        art["score"] = round(float(hit.get("$p", 0)), 3)
        out.append(art)
        if len(out) >= limit:
            break
    return out


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
