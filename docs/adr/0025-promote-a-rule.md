# 0025. Promote a mined rule into the rule set

**Date:** 2026-09-27
**Status:** approved in principle (CPO, 2026-09-27) — next after `c0ad20d` deploys

## Context

The demo's copy promises a promotion step three times: Rule Mining labels
strong candidates "Ready to promote", the Overrides page says a pattern
"can be promoted directly into the rules table", and the governance
stepper reads "Audit corrections, promote candidates". There is no button
and no endpoint. Antti's use-case review hit the gap directly.

Building it exposed a larger problem: **there is nothing to promote into.**
Invoice Processing passes `mine_rules_for_customer(...)` straight into
`check_rules` as the active rule set (`app.py`, the invoices endpoints).
Every rule the miner finds is applied immediately. Mined and active are
the same set, so the governance story the pages tell — a human reviews a
candidate, then promotes it — does not happen. A rule nobody looked at
routes invoices the moment its support crosses 95%.

That is also why a counting bug in rule support (the multi-key `relate`
condition, fixed in `c0ad20d`) changed which invoices were routed by rule,
not just what a report displayed.

`rule_revisions` already exists as an append-only history with
`valid_from` / `valid_to`, written by `snapshot_rules_to_revisions`. Two
things about it are not what they claim:

- The snapshot docstring says it "closes any open revisions" for rules no
  longer mined. It does not; it only appends. Open revisions accumulate.
- `src/data_loader.py` declares `rule_revisions.approver` as a link to
  `employees`, but the live table was created before that and has no link.
  It is also still a v1 table, so `relate` / `$patterns` cannot run over
  rule history.

## Decision

### 1. Active rules are promoted rules

Invoice Processing applies only rules with an **open promoted revision**:
a `rule_revisions` row for the tenant with `change_reason = "promoted"`
and `valid_to` null. Mining proposes; promotion activates.

This changes live behaviour: a tenant with no promoted rules routes
everything through `_predict`. The demo seeds each tenant's current strong
rules as promoted at load time, so the demo path looks the same on day
one — but the mechanism behind it becomes the one the copy describes.

### 2. A Promote action on strong candidates

Rule Mining and the Overrides patterns gain a **Promote** button on
candidates at ≥ 95% support. `POST /api/rules/promote` writes one
revision row carrying the rule and its support at promotion time, and
closes any open revision for the same `(vendor, target)` it supersedes.
**Demote** is the same endpoint closing the open row with
`change_reason = "demoted"`.

Recording the support at promotion time is what lets drift mean
something: the Rules page already compares current precision against
first precision, and "first" becomes "when a person approved it".

### An API another demo can mirror

This is also the reference implementation of the agent storyline's
governance use case, so the endpoint is shaped around the governance
act rather than around GL codes:

```
POST /api/rules/promote   {customer_id, rule: {conditions: [{field, value}],
                                                target: {field, value}},
                           support: {match, total}, reason}
POST /api/rules/demote    {customer_id, rule_id, reason}
GET  /api/rules/active    ?customer_id=
```

`conditions` is a list even though `check_rules` matches on vendor
alone today, and `target` names its field, so the same shape carries an
approver rule or a multi-clause `$patterns` rule without a new endpoint.
The response returns the revision row that was written, which is the
audit record: who, when, with what evidence.

### 3. Fix what the table claims

- Make `snapshot_rules_to_revisions` close revisions it supersedes, as its
  docstring says — or rename it to what it does. It becomes a report, not
  a way rules get activated.
- Recreate `rule_revisions` as a collection with the `approver` link the
  code already declares (plan item 7), so rule history is queryable with
  `relate`.

## Aito usage

None new. Reads are `_query` on `rule_revisions`; writes are the existing
batch insert. The promotion gate is application logic, deliberately:
which rules a business trusts is a governance decision, not an inference.

## Acceptance criteria

- A mined rule does not route an invoice until someone promotes it.
- Promoting a candidate makes the next matching invoice route by rule,
  and the Rules page shows it with its promotion-time support.
- Demoting it returns those invoices to `_predict`.
- `rule_revisions` never holds two open promoted rows for the same
  `(customer_id, vendor, target)`.
- `./do check` asserts that the invoices endpoint's rule set equals the
  open promoted revisions, not the miner's output.

## Demo impact

`docs/demo-script.md` gains the governance beat the copy already implies:
mine → review the evidence → promote → watch the next invoice route by
rule. The day-one demo looks unchanged because of the seeded promotions.

## Out of scope

- Approval workflows, roles, or who is allowed to promote.
- Automatic demotion on drift. Drift is surfaced; acting on it is human.
- Rules on inputs other than vendor. `check_rules` matches vendor only,
  and multi-clause rules from `$patterns` would need their own matcher.
