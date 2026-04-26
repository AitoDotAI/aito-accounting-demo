"""Help system: search + ranking + impression/click logging.

Three article categories: app (product docs), legal (compliance
pointers), internal (per-customer guidance).

Ranking strategy:
  - Default surface: top-K articles by historical click-through-rate
    where (customer_id, page) matches the current context.
    Aito's _predict article_id WHERE page=…, customer_id=… returns
    articles ranked by association — articles that historically get
    clicked from this page on this customer surface higher.
  - Search: same _predict but with a free-text query field added
    to the where clause. Aito's text analyzer takes care of token
    matching against title/body/tags.

Logging: every shown article writes an impression row, every click
toggles its clicked flag. The next prediction includes that signal.
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
    """Return ranked help articles for the current context.

    Articles available to a customer = those with customer_id="*"
    (global app/legal docs) plus their own internal ones. Aito's
    _predict returns ranked article_ids; we hydrate to full rows.
    """
    where: dict = {}
    if page:
        where["page"] = page
    # query goes through Aito's text analyzer if provided
    if query:
        where["query"] = query
    # We can't OR on customer_id in a single _predict call cleanly,
    # so we do two passes (global + customer-specific) and merge.

    ranked: list[tuple[float, str]] = []  # (score, article_id)

    for cid_filter in ("*", customer_id):
        try:
            result = client._request("POST", "/_predict", json={
                "from": "help_impressions",
                "where": {**where, "customer_id": cid_filter, "clicked": True},
                "predict": "article_id",
                "select": ["$p", "feature"],
                "limit": limit,
            })
        except AitoError:
            continue
        for hit in result.get("hits", []):
            ranked.append((float(hit.get("$p", 0)), hit["feature"]))

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

    # Hydrate: fetch all candidate articles and order by ranked list
    articles_by_id: dict[str, dict] = {}
    try:
        # One bulk fetch covering all candidates
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
