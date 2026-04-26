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

    Articles available to a customer = those with customer_id="*"
    (global app/legal docs) plus their own internal ones. We do two
    `_recommend` passes (global + customer-specific) and merge —
    Aito's `where` doesn't OR cleanly on customer_id without a $or
    expression, and two passes keep the where clauses simple.
    """
    base_where: dict = {}
    if page:
        base_where["page"] = page
    if query:
        # query goes through Aito's text analyzer
        base_where["query"] = query

    ranked: list[tuple[float, str]] = []  # (score, article_id)

    for cid_filter in ("*", customer_id):
        try:
            result = client._request("POST", "/_recommend", json={
                "from": "help_impressions",
                "where": {**base_where, "customer_id": cid_filter},
                "recommend": "article_id",
                "goal": {"clicked": True},
                "select": ["$p", "feature"],
                "limit": limit,
            })
        except AitoError:
            continue
        for hit in result.get("hits", []):
            # Aito returns dicts with "feature" (the value) and "$p"
            # (probability the goal would be achieved). Some payloads
            # also use "$value" — handle both shapes defensively.
            article_id = hit.get("feature") or hit.get("$value")
            if article_id is None:
                continue
            ranked.append((float(hit.get("$p", 0)), article_id))

    # Sort by score, dedupe
    seen = set()
    ordered_ids = []
    for score, aid in sorted(ranked, key=lambda x: -x[0]):
        if aid in seen:
            continue
        seen.add(aid)
        ordered_ids.append(aid)
        if len(ordered_ids) >= limit:
            break

    if not ordered_ids:
        # Cold start: fall back to category=app articles + customer's internal
        try:
            global_result = client.search("help_articles", {"customer_id": "*"}, limit=limit)
            internal_result = client.search(
                "help_articles", {"customer_id": customer_id}, limit=3,
            )
            return (internal_result.get("hits", []) + global_result.get("hits", []))[:limit]
        except AitoError:
            return []

    # Hydrate: fetch each article and preserve the ranked order
    articles_by_id: dict[str, dict] = {}
    try:
        for aid in ordered_ids:
            res = client.search("help_articles", {"article_id": aid}, limit=1)
            if res.get("hits"):
                articles_by_id[aid] = res["hits"][0]
    except AitoError:
        return []

    return [articles_by_id[aid] for aid in ordered_ids if aid in articles_by_id]


def log_impression(
    client: AitoClient,
    article_id: str,
    customer_id: str,
    page: str,
    query: str = "",
    clicked: bool = False,
) -> None:
    """Record that an article was shown (or clicked) for ranking."""
    row = {
        "impression_id": f"IMP-{uuid.uuid4().hex[:12]}",
        "article_id": article_id,
        "customer_id": customer_id,
        "page": page,
        "query": query,
        "clicked": clicked,
        "timestamp": int(time.time()),
    }
    try:
        client._request("POST", "/data/help_impressions", json=row)
    except AitoError:
        pass  # best-effort
