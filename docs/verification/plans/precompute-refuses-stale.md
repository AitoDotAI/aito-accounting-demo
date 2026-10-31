# Plan — a precompute missing what its page reads is refused

Branch `fix/precompute-refuses-stale` · head `a99b358` · **plan, not a report**

Ticket td-20261030211357041898. The symptom was "0 of 8 payments matched
by Aito" while the matcher measured 25/25.

## What the branch claims

| Criterion | Result |
|---|---|
| A `matching_pairs` payload without `metrics.matched_by_aito` is refused and the page falls through to live | |
| A payload whose pairs carry no `matched_by` is refused the same way | |
| An `anomalies_scan` payload whose flag text states a probability as a row count is refused | |
| The refusal prints once per (customer, payload), not once per request | |
| The refusal names what to run (`./do precompute-v2`) | |
| A current payload is served unchanged, with no extra Aito work | |
| Nav badges follow the page: a refused payload gives `null`, and the nav prints nothing rather than 0 | |

## Steps

```bash
./do test                 # 311 pass
```

Then, against a running server with devtools open:

1. Pick a tenant with a precompute. Note the matching page's headline
   numbers and the nav badge beside *Payment Matching*.
2. Edit `data/precomputed/v2/<T>/matching_pairs.json` to delete
   `metrics.matched_by_aito`.
3. Reload. Expect: real numbers on the page (computed live, slower), one
   warning line in the server log, and a nav badge that **agrees with
   the page or is absent** — never 0 beside a non-zero page.
4. Reload twice more. Expect no further warning lines.
5. Restore the file; confirm the page is instant again.
6. Repeat 2–5 for `anomalies_scan.json`, replacing a flag's
   `description` with the old `"91 of 100 historical invoices"` wording.

## What to capture

- The server log line, and proof it appeared once across three reloads.
- Screenshot pairs: the page and the nav badge together, stale vs
  restored. The badge-vs-page contradiction is the regression this
  branch's own guard caused, so it is the one to show.
- `X-Aito-Ms` for the refused load (live, hundreds of ms to seconds) and
  the served load (near zero).

## Tried to break it

- A payload with `metrics` present but empty.
- A payload with `pairs: []` and correct metrics — an empty ledger is
  legitimate and must still be served, not refused.
- A payload for a name with no staleness check declared
  (`invoices_pending`): must pass through untouched, checks are opt-in.
- Nothing in the store at all: must be indistinguishable from no
  precompute, i.e. live.
- `/api/nav/badges` for a tenant with nothing precomputed and nothing
  cached: all three values `null`. Then warm one page and re-ask; that
  one becomes a number while the others stay `null`.
