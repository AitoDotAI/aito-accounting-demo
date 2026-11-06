# Verification — the browser steps for the stack

Run 2026-11-06 against a **local Aito v2.12.0** (loopback, 4 GB container, a
15-tenant slice of the demo data, CUST-0000 not loaded) and a frontend built
from main `f856dd4` in its own worktree (`npm ci` + `next build`, no symlinked
`node_modules`). Nothing ran against shared. Driven in Chrome; network rows are
from the browser's own request log. Screenshots are in
`docs/verification/screenshots/browser-pass/`.

| # | Branch / PR | What was done | Observed | Screenshot |
|---|---|---|---|---|
| 1 | matching explain (#65) skeleton | open `/matching/?customer_id=CUST-0127` on a cold live pairing | skeleton rows and "Loading" in the header until the pairing returns (~5 s) | 01 |
| 2 | matching explain, one explain per opened row | open the page, click the 2nd row | the page makes `pairs` + **one** `explain` for the auto-opened first row; the click adds exactly one more (that row's invoice). No background requests for the other rows | 02 |
| 3 | matching explain, drift | rewrite the next explain request to a wrong `invoice_id`, click row 3 | server **409**; the row says "This row cannot be explained: the ledger has changed since the list was built, so re-running the pairing no longer arrives at this match. Reload to see the current matches." | 03 |
| 4 | matching explain, tenant switch | switch CUST-0127 -> CUST-0100 in the picker | every CUST-0127 row is gone; the table, the expanded row and the header are CUST-0100's; no CUST-0127 id anywhere in the page text | 04 |
| 5 | matching explain + precompute (#65, #66) | store a precompute written by `precompute_matching`, reload, click a row | `pairs` served from it, **no `explain` request at all** (the explanations are inline) | 08 |
| 6 | stale precompute (#66) | store a payload without `matched_by_aito` for CUST-0128, open the page | the server logs "ignored: metrics.matched_by_aito is missing ... Serving live"; the page shows the live numbers (6 by Aito, 2 by reference, 0 unmatched), not the stale payload's 7 unmatched; `/api/nav/badges` was `null` before the live page existed and 0 after, agreeing with the page | 06 |
| 7 | approver scope (#62) | Quality > Invoice Processing > target Approver, Re-run, CUST-0127 | 100 cases, every `predicted` is `CUST-0127-EMP-0000`; zero foreign ids on the page | 05 |
| 8 | evaluate input allow-list (#62) | Help Recommendations > target Article id, Re-run | request is `input_fields=page` (the stale `article_id` selection is dropped by the page) -> 200, no 400 | - |
| 9 | anomaly counts (#68) | open Anomaly Detection for CUST-0127 | "10 of 11 of this customer's invoices from Aluminium Constructions Alconst Oy use GL 6200 ..." and "9 of 10 ... Admark Oy use GL 1600"; the fixture has exactly 11 and 10 invoices with 10 and 9 on those GLs | 07 |

## A regression this pass found (fixed in #75)

Row 2's first screenshot (02) shows the live page's first row with a badge of
**0.83** above an explanation that adds up to **71%**, and an average card of
**0.82** where the mean of Aito's probabilities is 0.65: the disagreement #53
removed. Since #65 the live list ships no explanation until a row opens, and
`shownMatchScore` used "has an explanation" to decide which number to show, so
every live pair showed the blend. The precomputed page was right (08). Fixed in
#75 (pairs say whether they are a substitute; the page shows `model_p` for the
rest); screenshot 09 is the live page afterwards. None of the unit tests or the
whole-main pass could have seen it: it is a property of what the page shows.

## Not done

- The retry link on a failed explain ("The explanation could not be fetched.
  Try again"): it needs a 5xx or a dropped connection from the explain endpoint
  and none was forced.
- The nav badge's visible dot for matching (a 0 badge is not rendered, so row 6
  rests on the API value and the page).
- `/api/cache/status` and the L2 counters have no UI.
- Seen, not caused here: opening `/matching/?customer_id=X` first requests the
  default tenant's (CUST-0001) pairs and its first explain, then X's, because
  the customer context resolves after the first render. With the auto-opened row
  that is one wasted live `explain` per such load; before #65 it was a wasted
  `$why` for every row.
