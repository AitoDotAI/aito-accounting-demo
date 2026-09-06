# Cutting production over to the Aito v2 API

The demo runs on v1 by default and nothing here changes that until it is
run deliberately. This is the staged sequence for moving
`accounting.aito.ai` onto v2, with a way back at every step.

The order matters: **the app moves to v2 before the data moves to
master.** That way the new data is proven by the live application, on a
branch, while master still holds the old state and can be returned to by
unsetting one variable.

**But do not linger on the branch.** Only master is kept hot in memory
on the shared instance; an environment branch is not, so every query
against it pays a cold cost that has nothing to do with the application.
Steps 2 and 3 belong in the same sitting — deploy, smoke-test, promote —
rather than a soak of days. Do the deep verification in step 1, against
the branch, *before* anyone is pointed at it.

This also revises a measurement in `docs/verification/aito-v2-ui.md`:
the 15 s–4½ min cold-view latencies recorded there were measured against
an env branch and attributed entirely to the missing precompute. Some of
that is the branch not being retained. Re-measure on master after the
promote before quoting those numbers again.

## The switch

`AITO_V2_ENV` selects the API generation and says where to read:

| value | meaning |
|---|---|
| unset | v1 against master — the production default |
| `v2-demo` | v2 against the environment branch `v2-demo` |
| `master` | v2 against master, no `/env/` segment |

`master` is a sentinel, not an environment. The API refuses
`/env/master/` outright, so the one name that cannot denote a branch is
free to mean "no branch". See `resolve_env` in `src/aito_v2_client.py`.

## Before you start

- `./do check` green on `main`
- The instance's build is known: `curl -s https://shared.aito.ai/version`.
  If it moved since the branch was built, repair the branch — see step 1.
- `./do audit` clean against whatever the app currently reads
- A backup env exists (step 0 below). Promote **replaces** master; the
  backup is the only way back.

---

## 0. Snapshot master

```bash
# copy-on-write, instant, costs nothing until master diverges
POST /api/v2/_envs  {"name": "master-pre-v2-YYYYMMDD", "basedOn": "env.master"}
```

Rolling back later is `POST /api/v2/_envs/master-pre-v2-YYYYMMDD/promote`.

## 1. Build the new state on a branch

```bash
./do generate-data --medium          # regenerates EVERYTHING (see caveat)
AITO_V2_ENV=v2-demo ./do v2-build --reset
```

Master is untouched and still serving throughout.

**If the instance has been upgraded since the branch was built, repair
it first.** A v2 binary-format change auto-migrates master but *not*
environment branches, so a branch built on an older build fails plain
reads until each collection is rebuilt:

```bash
# once per COLLECTION — rep1 `type: table` tables are unaffected
for T in bank_transactions corporate_entities customers employees \
         help_articles help_impressions invoices overrides; do
  curl -sS -X POST -H "x-api-key: $AITO_API_KEY" \
    ".../db/aito-accounting-demo/env/v2-demo/api/v2/data/$T/repair"
done
```

The failure does not name itself. It surfaces as an internal error on a
query that has nothing to do with the upgrade —
`slice [1090930175543, 1090930175543] ouf of bounds [0, 41573889]` on a
plain `get`, or `ListSeqRepIoType expected 8 entries in OrderDir, got 6`
on `_estimate`. Nothing in either message says "format" or "repair".
Read an internal error on a branch that master handles fine as this,
first, before bisecting anything.

The asymmetry bites exactly this runbook: a branch is by definition
older than master, so an upgrade lands on the branch and not on the
thing it was branched from. Tracked as td-20260906220805012114; a core
fix is planned.

Verify the branch before anyone sees it:

```bash
./do audit --v2 --env v2-demo --accuracy   # coherence + every field beats its base rate
./do eval-matching --v2 --env v2-demo --split-on-reference
```

## 2. Deploy the app pointed at the branch

In `aito-demo-server`'s `demos.config.yaml`, under the `accounting`
demo's `env:` map:

```yaml
      AITO_V2_ENV: v2-demo
```

Rebuild the image and deploy. Production now runs **v2 against the
branch**; master is untouched.

**Back out:** remove the variable and redeploy. Instantly back to v1 on
master, with the old data intact.

Watch here — but briefly. This is the step where the application, not a
test, decides whether v2 is ready, and a smoke test is what it is for:

```bash
./do verify-demo --base https://accounting.aito.ai
```

Expect it to be slower than it will be after the promote, because the
branch is not held hot. Judge correctness here and latency after step 3.

## 3. Promote the branch into master

```bash
POST /api/v2/_envs/v2-demo/promote
```

Atomic swap. Master now holds the new state; the branch is not deleted
and continues to reference the same content.

Do this **soon after step 2, not days later** — see the memory note at
the top. Master is the only state kept hot, so until you promote, the
demo is paying a cold cost on every query.

**Immediately afterwards, clear the precompute** — see the caveat below.
It is stale the instant this completes.

**Back out:** promote the step-0 backup.

## 4. Point the app at master

```yaml
      AITO_V2_ENV: master
```

Rebuild and deploy. The app now reads master over v2 and no longer
depends on a branch existing. Delete the branch once you are happy:

```bash
DELETE /api/v2/_envs/v2-demo
```

**Back out:** set it back to `v2-demo`, which still references the same
content.

---

## Caveats that will bite

**Precompute goes stale at promote, silently.** `precompute_entries`
holds payloads computed from the previous data. Invoice ids are stable
(`CUST-0000-INV-000042` always exists) but the vendor, amount and date
behind one all change, so the app would serve precomputed views that
disagree with the database — no error, just wrong. Clear the table at
promote, then rebuild:

```bash
POST /api/v1/data/_delete  {"from": "precompute_entries"}
AITO_V2_ENV=master ./do precompute-v2 --limit 5 --workers 2   # demo tenants first
```

Until that finishes, heavy views compute live: 15 s to 4½ min each.
Precompute the tenants you intend to show before presenting, and confirm
with `./do verify-demo`, which flags any step slow enough to look broken.

**Regeneration changes everything, not just the new fields.** The
generator seeds per-customer RNG with `hash(customer_id)`, which Python
randomises per process, so no two runs produce the same data. Every
number quoted in `docs/demo-script.md`, the README and the verification
report is from the previous dataset, as are the committed bootstrap
files (`data/precomputed/landing.json`, `help_related.json`) and the
screenshots. Re-measure and re-capture after the cutover.

**A format change between verification and promote would go unnoticed.**
The repair in step 1 fixes the branch at that moment; nothing rechecks
it later. If the instance is upgraded in the window between step 1 and
step 3, re-run the repair and re-run `./do audit` before promoting —
otherwise the state you promote into master is one nobody has read since
the upgrade.

**Master's storage engine changes.** Master currently holds rep1
`type: table` tables; the branch holds rep2 `type: collection`
collections, so promote switches it. v1 requests are engine-dispatched
onto collections through the v1x adapter, and this was checked before
the cutover — `$match` on master over v2 returns hits — but
`accounting.aito.ai` would be the first real application on that path
rather than a fixture. Worth knowing on the day.

**The help drawer is still on v1** and reads master directly, so between
steps 2 and 3 it serves the *old* data while every other view serves the
branch. Tenant scoping is unaffected. Migrating it is tracked
separately.
