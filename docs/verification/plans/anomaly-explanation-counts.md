# Plan — an anomaly flag states a count it has, or a probability it has

Branch `fix/anomaly-explanation-counts` · head `cb749e8` · **plan, not a report**

The old wording printed `int($p * 100)` as "N of 100 historical
invoices": a smoothed posterior presented as a row count, over a
population that was never the customer's.

## What the branch claims

| Criterion | Result |
|---|---|
| A GL-mismatch flag with complete history reads "N of M of this customer's invoices from <vendor> use GL X" | |
| M is the real number of that customer's invoices from that vendor, counted, not a page size | |
| A predicted GL the customer has never used reads "None of this customer's M invoices…" and gives p | |
| A vendor new to the customer reads "no prior invoices… Aito predicts … at p=…" | |
| No flag anywhere says "of 100 historical invoices" | |
| The count query is scoped to `{customer_id, vendor}` and runs only on the gl_mismatch branch | |
| A truncated sample is not quoted as a count | |
| A failed count query does not read as an empty history, and logs | |
| `scripts/find_unfalsifiable_tests.py` reports no assertion-free test body whose intent is clear | |

## Steps

```bash
./do test                             # 323 pass
env -u PYTHONPATH uv run python -I scripts/find_unfalsifiable_tests.py tests
./do aito-check --v2
```

In the browser at `/anomalies`, you need one tenant per sentence form.
Find them first rather than hoping:

```bash
# tenants whose anomaly scan contains a gl_mismatch flag
grep -l '"category": "gl_mismatch"' data/precomputed/v2/*/anomalies_scan.json | head
```

For each candidate, read the flagged invoice's vendor, then count that
customer's invoices from it to predict which sentence should appear. If
the count is non-zero and includes the predicted GL → form 1; non-zero
without it → form 2; zero → form 3.

## What to capture

- One screenshot per sentence form, with the flag text legible.
- The `_search` body behind each: `{"customer_id": …, "vendor": …}` and
  the `total` in the response, to show M on screen equals M in Aito.
- The `X-Aito-Ops` for an anomaly page load, to confirm the count query
  appears once per gl_mismatch flag and not once per invoice.

## Tried to break it

- Find a (customer, vendor) pair with more than 1000 invoices, which is
  the truncation path. **If none exists in this dataset, say so in the
  report** — the guard is then unreachable in production and only the
  unit test covers it, which is worth recording rather than claiming
  coverage.
- Point the app at a tenant whose precompute still carries the old
  wording and confirm the staleness guard refuses it (that is branch 4's
  plan, but the two interact: without the guard this fix is invisible for
  the 11 affected files).
- Break the count query (bad credentials for the search, or a tenant id
  with a character the API rejects) and confirm the flag still renders,
  with the probability wording and a log line — not "no prior invoices",
  and not a missing flag.
- Check a flag whose predicted GL equals the stated GL: it should not be
  a gl_mismatch at all, so no count query should fire.
