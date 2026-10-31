# Plan — a warm cache reports warm in v2 mode

Branch `fix/cache-status-v2-prefix` · head `894b684` · **plan, not a report**

Independent of the review stack, found during the CPO's re-review.
`/api/cache/status` read `invoices:<tenant>` while every writer writes
`invoices:v2:<tenant>`, so all five flags were false however warm the
cache was.

## What the branch claims

| Criterion | Result |
|---|---|
| In v2 mode, a tenant whose pages have been computed reports `*_warm: true` | |
| A tenant with nothing computed reports `false` on all five | |
| All 15 page-cache call sites go through `page_cache_key` | |
| No hand-spelled page cache key remains in `src/app.py` | |
| v1 mode is unchanged (the prefix is empty there, so the old code was already right) | |

## Steps

```bash
./do test                 # 250 pass
```

With the backend on the v2 environment, pick a tenant that has **no**
precompute so the cache is the only warm layer (`CUST-0100` was used for
this in earlier work):

```bash
T=CUST-0100
curl -s "localhost:8200/api/cache/status?customer_id=$T"      # expect all false
curl -s -o /dev/null "localhost:8200/api/invoices/pending?customer_id=$T"
curl -s -o /dev/null "localhost:8200/api/quality/overview?customer_id=$T"
curl -s "localhost:8200/api/cache/status?customer_id=$T"      # invoices_warm, quality_warm now true
```

Then confirm the bug was real, by checking out `origin/main` and running
the same sequence: every flag should stay false after the pages are
warm. Without that comparison the report says nothing about what was
fixed.

## What to capture

- The three `cache/status` responses, before and after warming, on this
  branch — and the "after" response on `main` for contrast.
- `grep -n 'f"\(invoices\|quality\|matching\|rules\|anomalies\):' src/app.py`
  returning nothing.

## Tried to break it

- Warm only `matching` and confirm only `matching_warm` flips; a builder
  bug that collapsed the names would turn several true at once.
- Ask for a tenant that does not exist: all false, no error.
- Run against v1 (`AITO_V2_ENV` unset) and confirm the flags still work;
  `_V2` is empty there and a builder that hardcoded `v2:` would break it.
- Warm a page, then invalidate via the admin cache-drop endpoint, and
  confirm the flags go back to false.

## Note on the tests

The first version of this branch's tests passed with the bug reinstated:
they built the expected key by calling the function under test, and the
suite runs with `_V2` empty, where the buggy and correct builders return
the same string. Worth knowing if you extend them — assert against
literals, and set `_V2` explicitly.
