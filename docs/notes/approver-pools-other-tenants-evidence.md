# `approver` stores a name, so it pools other tenants' evidence

Measured 2026-09-08 against `env.v2-demo`.

## The inconsistency

`data/generate_fixtures.py:798-799` writes the two employee references
differently:

```python
"approver":  approver["name"],           # "Matti Niemi"
"processor": processor["employee_id"],   # "CUST-0000-EMP-0156"
```

So `src/data_loader.py` can link one and not the other — the link target
is `employees.employee_id`, and a name is not an id:

```python
"approver":  {"type": "String", "nullable": False},
"processor": {"type": "String", "nullable": False, "link": "employees.employee_id"},
```

`overrides.approver` has the same problem.

## Why it matters

Employee names are not unique across tenants. Of 519 distinct names in
1 216 sampled employees, **217 (42%) belong to more than one tenant**;
`Matti Hämäläinen` exists in 14 companies.

Because `approver` is that name, every tenant sharing it contributes to
the same value's statistics:

| value | instance-wide rows | CUST-0000's rows | share that is ours |
|---|---|---|---|
| `approver = "Matti Niemi"` | 645 | 12 | **1.9%** |
| `approver = "Matti Tuominen"` | 1 161 | 0 | 0% |
| `approver = "Matti Hämäläinen"` | 1 727 | 0 | 0% |
| `processor = "CUST-0000-EMP-0156"` | 329 | 329 | **100%** |

Predicting `approver` for CUST-0000 therefore learns one person's
approval habits from up to fourteen unrelated people. This is not a leak
of values that a filter can catch — it is contamination of the
statistics behind a value the tenant legitimately uses.

**The existing stop-gap does not help here.** `_drop_foreign_candidates`
keeps candidates whose value the tenant has used. `Matti Niemi` passes
that test, and arrives carrying 633 other companies' decisions. The
stop-gap only suppresses the visible symptom — foreign *names* in the
alternatives list — not the contamination underneath.

`processor` is unaffected: `employee_id` is tenant-prefixed, so its
evidence is 100% the tenant's own.

## Fix

Store the id and resolve the name for display, exactly as `processor`
does:

1. `generate_fixtures.py` — write `approver["employee_id"]`, in
   `invoices` and in `overrides`.
2. `data_loader.py` — add `"link": "employees.employee_id"` to both.
3. Anywhere the approver is rendered, resolve through the link
   (`approver.name`) rather than printing the stored value.
4. Then `approver.customer_id` scopes the candidate domain the same way
   `invoice_id.customer_id` now scopes payment matching (commit
   29161fa), and `_drop_foreign_candidates` can be deleted rather than
   extended.

This needs a schema change and a data reload, so it belongs **in** the
cutover regeneration rather than as a second pass afterwards.

## Caveat

Names colliding across tenants is a property of this fixture's name
pool, not necessarily of production data — but a real multi-tenant AP
system has the same exposure the moment two customers employ people with
the same name, which at any scale is a certainty rather than a risk.
