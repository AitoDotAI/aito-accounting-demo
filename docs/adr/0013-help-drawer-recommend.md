# 0013. Help drawer ranked by `_recommend` over impressions

**Date:** 2026-04-26
**Status:** accepted

## Context

The demo needs a help system — both because users need it ("what
does $why mean?"), and because it's a chance to demonstrate Aito's
recommendation pattern alongside the prediction pattern that drives
the rest of the app.

aito-demo (the grocery store reference) shows `_predict` for product
ranking and `_recommend` for personalized suggestions. We can do
the same here: rank help articles by their historical
click-through-rate per (page, customer, query) context, with
"users who read this also read" as a follow-on `_recommend`.

## Decision

Two-table click-stream pattern:

- `help_articles` — 120 articles, mix of global and per-customer,
  categorised app/legal/internal.
- `help_impressions` — 14,500 rows of `(article_id, customer_id,
  page, query, clicked, prev_article_id)`. Each shown article is
  one impression; each click sets `clicked=true`. The
  `prev_article_id` chains sessions so we can mine "users who read
  X also read Y."

Two endpoints, both `_recommend`-based:

1. **`GET /api/help/search`** ranks articles by historical click
   probability given the current `(page, customer, query)`
   context. Implemented as `_recommend` with `goal: {clicked: true}`.

2. **`GET /api/help/related?article_id=...`** ranks articles by
   `_recommend WHERE prev_article_id=…, goal: {clicked: true}`.
   The frontend tracks the user's last-clicked article and threads
   it as `prev_article_id` on the next impression.

Both endpoints cache 10 minutes server-side (key includes the full
context tuple) — the underlying `_recommend` runs ~100-200 ms
under load and the result for a (customer, page, query) tuple is
stable across users.

## Aito usage

```javascript
// help/search
{
  from: "help_impressions",
  where: { customer_id: "CUST-0000", page: "/invoices" },
  recommend: "article_id",
  goal: { clicked: true },
  limit: 5,
}

// help/related
{
  from: "help_impressions",
  where: { customer_id: "CUST-0000", prev_article_id: "ART-INVOICES-101" },
  recommend: "article_id",
  goal: { clicked: true },
  limit: 4,
}
```

A second pass filters the result by `help_articles WHERE
customer_id IN ("*", "CUST-0000")` — Aito sometimes relaxes the
where filter and returns articles outside the customer's
eligibility set, so we enforce the visibility rule explicitly.

## Acceptance criteria

- The "?" button bottom-right of the midpane opens the drawer.
- The drawer shows up to 5 articles, ranked by CTR for the current
  page + customer.
- Clicking an article logs `(clicked=true)` and shows up to 4
  "users who read this also read" articles below.
- Switching customer changes the article set (per-customer
  internal-policy articles appear/disappear).
- Empty query and "GL code" both return non-empty results in <2 s
  warm.
- Server-side cache returns cached responses in <5 ms.

## Demo impact

Adds a second Aito-pattern story to the demo: "the same database
that predicts GL codes also ranks help articles by click history."
Demonstrates `_recommend` (vs `_predict`) and the impression-based
feedback loop that drives the ranking — same loop a real product
would use for any in-app recommendation.

The "users who read this also read" widget is the smallest possible
demonstration of session-aware recommendations: `WHERE
prev_article_id` is one extra constraint, no separate data model.

## Out of scope

- **Per-user ranking.** All impressions are anonymized at the
  customer level — no `user_id`. A real product would condition on
  user role / department / recent activity for finer
  personalization.
- **Real-time impression flush.** Impressions are POSTed
  fire-and-forget. A burst of clicks won't immediately move the
  ranking because the index is optimized periodically. For demo
  purposes the existing 14,500-row history is enough that
  adversarial click patterns wouldn't move the top-N anyway.
- **Authoring UI.** Articles are bulk-loaded from
  `data/help_articles.json` at deploy time. Adding/editing in-app
  is not in scope.
