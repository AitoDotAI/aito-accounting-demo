# Verification plans

**A plan in this folder is not a verification report.** CLAUDE.md blocks a
merge until `docs/verification/<feature>.md` exists, and that file is the
output of the adversary pass: steps actually attempted, screenshots
actually taken, Aito calls actually observed, and failures actually found.
Nothing here is evidence of anything.

What these are: the design half of that pass, written up front so the
pass itself is fill-in rather than design. Each plan names what the
branch claims, the commands that exercise it, what to capture, and the
specific ways to try to break it. Written 2026-10-31 by the session that
wrote the branches, which is exactly why it is not also the session that
signs them off — the adversary is supposed to be someone else, and an
author listing the attacks on their own work will list the ones they
already thought of.

So treat the "tried to break it" sections as a floor, not a ceiling. The
most valuable thing a reviewer can do with one of these is think of an
attack that is not on the list.

## Using one

1. Copy the plan to `docs/verification/<feature>.md`.
2. Fill the Verdict and the Acceptance criteria table with observed
   results, in the shape of `docs/verification/0026-no-reference-payments-first.md`.
3. Add what you tried that is not in the plan, and what it did.
4. Delete the "What to capture" scaffolding once the evidence is in.

A criterion you could not check is recorded as not checked, with the
reason. An empty row is worse than an honest "not reached".

## Before running one

Check out the branch the plan names. Several of these describe endpoints
and flags that do not exist on `main` — `/api/matching/explain` is one —
so a plan run against `main` will look as though the feature is missing.
The branch heads the CPO reviewed on 2026-10-31 are in each plan's
subtitle; if a head has moved since, the plan may describe an older
shape.

## Setup common to all of them

```bash
# backend, against the v2 environment the demo serves
env -u PYTHONPATH AITO_V2_ENV=master uv run uvicorn src.app:app --port 8200
# or ./do dev-v2, which defaults AITO_V2_ENV to v2-demo instead

./do frontend-dev            # Next.js on :3000, proxying /api to :8200
```

On this NixOS host `env -u PYTHONPATH` matters for anything run through
`uv`; `./do` handles it. Timing and call counts come back on every
`/api/*` response as `X-Aito-Ms`, `X-Aito-Calls` and `X-Aito-Ops`
(`_search:16.7,_predict:1139.7`) — use those rather than wall clock when
comparing two settings, and record wall clock too when the question is
what a user waits (see `docs/notes/aito-perf-findings.md` §8).

Aito's own response time for one query class moved between 0.44 s and
6.6 s during the day and sat at a 603 ms median at 23:00. Do not read a
single slow page load as a regression.

## The plans

| Branch | Plan |
|---|---|
| `fix/evaluation-approver-scope` | [evaluation-approver-scope.md](evaluation-approver-scope.md) |
| `fix/book-replays-and-validate-customer` | [book-replays.md](book-replays.md) |
| `fix/matching-explain-on-demand` | [matching-explain-on-demand.md](matching-explain-on-demand.md) |
| `fix/precompute-refuses-stale` | [precompute-refuses-stale.md](precompute-refuses-stale.md) |
| `docs/aito-latency-is-not-the-app` | [aito-latency-findings.md](aito-latency-findings.md) |
| `fix/anomaly-explanation-counts` | [anomaly-explanation-counts.md](anomaly-explanation-counts.md) |
| `fix/cache-status-v2-prefix` | [cache-status-v2-prefix.md](cache-status-v2-prefix.md) |
