# Verification — Aito latency is not the app

Branch `docs/aito-latency-is-not-the-app`. As a merge unit it carries
branches 1-4; its own commits are three documents.

**Verified by:** a session that did not write the branch (the repo rule
asks for an independent adversary). Plan followed as a floor:
`docs/verification/plans/aito-latency-findings.md`.

**Environment.** Offline checks used a dummy Aito URL with the app's L2
cache unregistered, so nothing could be written to shared. Live checks
were read-only `_search`/`_predict`/`_relate` calls against shared v2
`master`, one at a time with gaps. **No `_evaluate` was sent to shared**
at the CPO's instruction, after `_evaluate` calls saturated it that
morning (429, inFlightWeight 30 of 32, then out of memory). The two
`aito-check` checks that use `_evaluate` were therefore not run:
`check_evaluate_baseline_is_scoped` and
`check_evaluate_approver_candidates_are_the_customers_own`. 15 of 17 live
checks passed; that is not the 16/16 the gate asks for, and it is
recorded here rather than rounded up.

**Not done:** browser/Playwright steps (screenshots, devtools network).
Rows that need them are left unticked.

## Results

| Criterion | Result |
|---|---|
| its own commits change only docs | yes |
| the claims in the findings document are reproducible | **could not check**: the plan's quiet-hours medians do not reproduce in daylight, by design, and `_evaluate` is off limits on shared |

## Findings

None beyond those in branches 1-4. Recorded honestly as "could not check"
rather than ticked.
