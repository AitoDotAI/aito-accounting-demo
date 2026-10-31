# Plan — the latency findings in §8 are reproducible

Branch `docs/aito-latency-is-not-the-app` · head `abeb9c0` · **plan, not a report**

Documentation only: no code changes, so there is no feature to break.
What needs verifying is whether the numbers and the method survive
someone else running them. Tickets td-20261030214404054563 and
td-20261030220110025872.

## What the branch claims

| Criterion | Result |
|---|---|
| The app is not 3× slower than a script: paired interleaved n=9 gives a median of −2367 ms, app slower in 1 of 9 | |
| Aito's own time for one `$why` query class ranged 0.44–6.6 s during the day | |
| At 23:00, one query in flight: median 603 ms, max 1247 ms over 60 asks, none over 2 s | |
| 1 → 2 → 4 of our own queries in flight: Aito time 612 → 1174 → 1225 ms | |
| Wall minus `x-aitoai-response-time` grows to 1157 ms median at 4 in flight | |
| Capping the fan-out at 2 does not help: median +29 ms, slower in 6 of 12 | |
| A repeat ask has no systematic advantage for `$why` ranking queries | |
| The order effect on form-fill pairs was 100–235 ms, larger than the effect under test | |

## The honest framing for whoever runs this

**A daytime re-run will not reproduce the quiet-hours numbers, and that
is the finding, not a failure.** The claim is that the width tracks time
of day, so a daytime median above 603 ms supports §8 rather than
contradicting it. What must reproduce is the *method* and the two
structural results:

- the saturation shape (Aito's own time stops growing past ~2 in flight
  while wall time keeps going), and
- that capping our fan-out at 2 buys nothing.

If a daytime run shows Aito's own time exceeding ~2 s at 4 in flight,
that is new information and §8 needs amending — it would mean our own
concurrency can reach the tail after all.

## Steps

The probe scripts were written in a session scratchpad and are not in the
repo. Rebuild them from §8, which states the shape of each: same query
class (`matching_service.ranking_query(..., explain=True)`), fresh
tenants, paired and interleaved, alternating order, `x-aitoai-response-time`
recorded alongside wall clock.

Caps worth keeping, because this is a customer-facing instance: ≤1 qps
for the quiet baseline, ≤120 s per concurrency step, abort any run where
a single query exceeds 10 s.

## What to capture

- Per-condition medians, p90, max and n — not means; the distribution is
  the point and one 6.6 s sample moves a mean.
- Both numbers for every sample: Aito's header and wall clock. §8's
  correction to the old advice is precisely that the header alone
  under-reports what a user waits.
- The time of day of each run, prominently.

## Tried to break it

- Re-run the paired app-vs-script test at n=5 and confirm it reads the
  *other way* (§8 records −35 ms with the app slower in 2 of 5). That is
  the strongest check on the method: if n=5 is stable, the n=9 result was
  not needed and the doc overstates the care required.
- Run the concurrency steps in reverse order (4, 2, 1). A load-order
  confound would show up as a different shape.
- Check whether another session is hammering the instance during the run.
  A transient nginx 502 was seen at 23:15 on 2026-10-30; a run that
  overlaps someone else's traffic measures their load, not ours.
