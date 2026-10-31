# Plan — the book replays, and its assertions can fail

Branch `fix/book-replays-and-validate-customer` · head `efc6f66` · **plan, not a report**

Ticket td-20261030204426717396. Mostly a command-level pass: the book is
the artefact, not a page.

## What the branch claims

| Criterion | Result |
|---|---|
| `./do book` runs 30/30 with no "cannot replay" | |
| `./do prove-assertions` reports every book assertion able to fail | |
| All 21 `assertln` calls pass the condition first, so none is vacuous | |
| `./do book-accept` refuses a baseline where two entities share one measurement | |
| `--i-know` overrides that refusal, and says so | |
| Removing `validate_customer()` changed no behaviour: a bad customer_id is still a 400 | |

## Steps

```bash
./do book                 # 30/30
./do prove-assertions     # every assertion broken in turn, each must fail
./do test                 # 282 pass
```

For the baseline guard, make a collision on purpose:

1. Edit a baseline under `books/book/` so two entities carry one
   measurement (the shape `scripts/baseline_collisions.py` looks for).
2. `./do book-accept` — expect a refusal naming the file and the two
   entities.
3. `./do book-accept --i-know` — expect it to proceed and say it was
   overridden.
4. `git checkout` the baseline.

For the removed validator, with the server running:

```bash
curl -si 'localhost:8200/api/invoices/pending?customer_id='          | head -1
curl -si 'localhost:8200/api/invoices/pending?customer_id=NOPE'      | head -1
curl -si 'localhost:8200/api/matching/pairs?customer_id=NOPE'        | head -1
```

All three should be 4xx. `validate_customer_middleware` (`src/app.py`)
is what enforces it; the function removed on this branch was dead.

## What to capture

- Full `./do book` and `./do prove-assertions` output.
- The refusal text from `book-accept`, and the override line.
- The three curl status lines.

## Tried to break it

- Run `./do book` twice. Snapshot-keyed HTTP replay should give
  byte-identical output; a diff on the second run means a test is
  reading something not in its snapshot.
- Delete one snapshot file and run `./do book`: expect a clear "cannot
  replay" rather than a silent live call.
- Point a book test at a tenant that has none of the category it
  conditions on (the `test_08` defect this branch fixed) and confirm it
  fails loudly rather than reporting an empty result as a pass.
- In `prove-assertions`, check it is actually breaking conditions and not
  just messages — an `assertln(True, …)` can never fail and must be
  reported, not passed.
