# Plan — only the expanded row asks why, and it asks about itself

Branch `fix/matching-explain-on-demand` · head `1679d93` · **plan, not a report**

Ticket td-20260909115133919692, plus the identity guard the CPO review
of 2026-10-31 added.

## What the branch claims

| Criterion | Result |
|---|---|
| The ranking `_predict` selects no `$why` — the list is 5.1 KiB of Aito response, not 74.6 | |
| `/api/matching/pairs` payload is ~3.0 KiB, down from ~7.1 | |
| Expanding a row fetches `/api/matching/explain` and renders the factors | |
| The explanation re-issues the SAME `where` and limit as the ranking | |
| Explanations prefetch serially after the list renders, so no first click waits | |
| A reopened row is served from cache (~3 ms) | |
| `/api/matching/explain` requires `invoice_id` and 409s when it differs from the pairing | |
| A refused cache entry is evicted, so the next ask recomputes instead of re-409ing | |
| A failed fetch can be retried from the row | |
| The failure text does not claim "the match itself stands" on 404/409 | |

## Steps

```bash
./do test                 # 297 pass
./do eval-matching        # accuracy unchanged by moving explanations
```

In the browser at `/matching`, with devtools Network open:

1. Load the page for `CUST-0000`. Record the `/api/matching/pairs`
   response size and `X-Aito-Ops`.
2. Confirm `$why` appears in no request body on load.
3. Expand row 1. Record `/api/matching/explain`, its `X-Aito-Ms`, and
   that its `_predict` body carries `$why` with the highlight tags.
4. Collapse and re-expand. Expect no new request.
5. Watch the background prefetch chain: one `/explain` at a time, in row
   order, starting after the list paints.

## What to capture

- The two response sizes (list with and without — the "without" figure
  needs `git stash` of this branch's `matching_service.py` change, or
  take the 74.6 KiB figure as given and say so).
- The ranking body and the explain body side by side, to show the
  `where` and `limit` match.
- Screenshots: a rendered why panel; the skeleton state during a slow
  fetch; the retry link after a failure; the drift message.

## Forcing the drift case, which is the whole point of the guard

The 409 fires when the row's invoice and the recomputed pairing's
invoice differ. Live, that needs the ledger to move between the
precompute and the click. To produce it on purpose:

1. Serve a tenant that has a precompute (`data/precomputed/v2/CUST-0000/`).
2. Edit `matching_pairs.json`: change one pair's `invoice_id` to another
   open invoice's id, keeping `matched_by: "aito"`.
3. Reload `/matching`, expand that row.
4. Expect the "the ledger has changed … no longer arrives at this match"
   message — **not** a why panel, and not a panel describing the other
   invoice. If a panel renders with factors naming an invoice other than
   the row's, the guard has failed and that is a blocker.
5. Reload again and confirm the second attempt recomputes (the entry was
   evicted) rather than answering 409 from cache.
6. `git checkout` the precompute file.

## Tried to break it

- Expand a row matched by reference. Expect no `/explain` call at all —
  there is no prediction to explain.
- Expand while the prefetch chain is mid-flight; the clicked row should
  not be skipped or served another row's answer.
- Kill the backend, expand a cold row, restart, click "Try again".
  Expect a successful fetch — before this branch the row was
  permanently unexplainable once `asked` had been marked.
- Switch tenant with a row expanded, then expand the same row index in
  the new tenant. The `asked` set and `why` map are keyed per tenant
  load; a leak here would render one tenant's explanation under
  another's row, which is the P1 class.
- Call `/api/matching/explain` without `invoice_id`. Expect 422 from
  FastAPI, not an answer.
