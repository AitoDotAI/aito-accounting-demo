# Help recommendations — CTR-ranked articles

*The same recommendation pattern aito-demo uses for product
suggestions, applied to in-app help. Every shown article is an
impression; every click trains the next ranking.*

**Companion to [aito-demo's recommendations](https://github.com/AitoDotAI/aito-demo/blob/main/docs/use-cases/01-recommendations.md)** — same `_recommend` pattern, applied to help articles
instead of products.

## Overview

The "?" button bottom-right of any view opens a help drawer. The
articles inside are ranked by historical click-through-rate
(CTR) per `(page, customer)` context. Click an article → see
"Users who read this also read…" via session chaining.

## How it works

### Two impressions tables

```
help_articles            help_impressions
  article_id (pk)         article_id (link)
  title (Text)            customer_id (link)
  body (Text)             page (String)        # /invoices, /matching, ...
  category (String)       query (Text)         # search query if any
  customer_id (String)    clicked (Boolean)    # true if user clicked
  tags (Text)             prev_article_id      # for session chaining
```

Every article shown produces an impression with `clicked=false`.
The impression updates to `clicked=true` if the user clicks. The
session is chained via `prev_article_id` — the article the user
was reading before clicking the next one.

### CTR ranking

```python
# src/help_service.py — search_help()
client._request("POST", "/_recommend", json={
    "from": "help_impressions",
    "where": {"customer_id": customer_id, "page": page},
    "recommend": "article_id",
    "goal": {"clicked": true},
    "limit": 5,
})
```

`_recommend` ranks `article_id` values by their conditional
probability of leading to `goal: {clicked: true}` given the
context. Articles users on this page tend to click rise to the top.

### "Users who read this also read"

```python
# src/help_service.py — related_articles()
client._request("POST", "/_recommend", json={
    "from": "help_impressions",
    "where": {"customer_id": customer_id, "prev_article_id": article_id},
    "recommend": "article_id",
    "goal": {"clicked": true},
    "limit": 4,
})
```

Same operator, conditioned on the user's previous click. Returns
the articles most-likely-to-be-clicked-next given that they just
read this one.

### Server-side cache

The drawer fires a search per debounced keystroke. `_recommend`
takes ~100-200 ms on a warm Aito index, but results are stable per
`(customer, page, query)` tuple — so the endpoint caches at the
server for 10 minutes:

```python
# src/app.py
@app.get("/api/help/search")
def help_search(...):
    cache_key = f"help_search:{customer_id}:{page}:{q}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    ...
```

After warmup the drawer responds in <5 ms.

## Demo flow

1. Click the "?" button → drawer slides in, articles load.
2. Type "GL code" → debounced search re-runs with the query in
   the where clause, articles re-rank.
3. Click an article → expanded body + "Users who read this also
   read" appears below with up to 4 suggestions. Each click logs
   an impression and chains `prev_article_id`.

## Aito features used

- **`_recommend`** — goal-oriented ranking
- **Schema links** — `help_impressions.article_id` ↔
  `help_articles.article_id`, so the response can include article
  title/body without a second query
- **Session chaining** — `prev_article_id` is just another field
  in the where clause, no special session API

## Out of scope

- **Per-user personalisation.** Impressions are anonymised at
  the customer level — no `user_id`. Real product would
  condition on user role for finer ranking.
- **Real-time impression flush.** Impressions are POSTed
  fire-and-forget. Bursty clicks won't immediately move the
  ranking because Aito's index optimises periodically.
