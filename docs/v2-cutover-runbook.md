# Cutting production over to the Aito v2 API

The demo runs on v1 by default and nothing here changes that until it is
run deliberately. This is the staged sequence for moving
`accounting.aito.ai` onto v2, with a way back at every step.

The order matters: **the app moves to v2 before the data moves to
master.** That way the new data is proven by the live application, on a
branch, while master still holds the old state and can be returned to by
unsetting one variable.

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

Watch here. This is the step where the application, not a test, decides
whether v2 is ready.

## 3. Promote the branch into master

```bash
POST /api/v2/_envs/v2-demo/promote
```

Atomic swap. Master now holds the new state; the branch is not deleted
and continues to reference the same content.

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
