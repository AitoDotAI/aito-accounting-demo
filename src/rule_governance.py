"""Which rules route invoices: the ones a person promoted. See ADR 0025.

Mining proposes; promotion activates. Before this, Invoice Processing
routed on every mined rule the moment its support crossed 95%, so no one
reviewed a rule before it changed how invoices were coded -- although the
Rule Mining, Overrides and governance copy all said someone did.

`rule_revisions` is the record. It is APPEND-ONLY: promoting, superseding
and demoting each add a row, and a rule's current state is its latest row.
Nothing is ever rewritten, so the table answers "who approved this rule,
when, on what evidence" for any point in time.

A rule is `{"conditions": [{field, value}], "target": {field, value}}`.
That is deliberately more general than the vendor -> GL rules routed
today, so an approver rule, a multi-condition `$patterns` rule, or the
agent demo's governance view can use the same calls.
"""

import json
import time
import uuid

from src import cache, cache_versions, precompute_store

REVISIONS_TABLE = "rule_revisions"

# Enough to read a tenant's whole revision history in one query. Checked
# rather than trusted: a truncated read would silently mis-state which
# rules are active.
_MAX_REVISIONS = 5000


class RuleNotActive(Exception):
    """Demote was asked for a rule that is not currently promoted."""


def rule_key(rule: dict) -> str:
    """Identity of a rule: its conditions and WHICH field it sets.

    The target VALUE is not part of it. Promoting "Europress -> 5400" while
    "Europress -> 5100" is active replaces it rather than leaving two
    contradictory rules open.
    """
    conditions = sorted((c["field"], str(c["value"])) for c in rule["conditions"])
    return json.dumps({"if": conditions, "sets": rule["target"]["field"]}, ensure_ascii=False)


def rule_name(rule: dict) -> str:
    """The display name, in the miner's format so a rule reads the same
    before and after it is promoted.

    The name is not cosmetic: Invoice Processing puts it in each routed
    invoice's explanation. A first cut named seeded rules "X -> 4400"
    where the miner says "X → GL 4400", and 9 of 15 invoices on the day-one
    comparison differed for that reason alone.
    """
    target = rule["target"]
    conditions = rule["conditions"]
    if target["field"] == "gl_code" and [c["field"] for c in conditions] == ["vendor"]:
        return f"{conditions[0]['value']} → GL {target['value']}"
    lhs = " AND ".join(f"{c['field']}={c['value']}" for c in conditions)
    return f"{lhs} → {target['field']} {target['value']}"


def _history(client, customer_id: str) -> list[dict]:
    result = client.search(REVISIONS_TABLE, {"customer_id": customer_id}, limit=_MAX_REVISIONS)
    if int(result.get("total", 0)) > _MAX_REVISIONS:
        raise ValueError(
            f"{customer_id} has {result['total']} rule revisions, more than the "
            f"{_MAX_REVISIONS} read -- the active set would be computed from a partial history")
    return [r for r in result.get("hits", []) if r.get("rule_key")]


def active_rules(client, customer_id: str) -> list[dict]:
    """Revisions whose latest event is a promotion, oldest promotion first."""
    latest: dict[str, dict] = {}
    for row in sorted(_history(client, customer_id), key=lambda r: r["valid_from"]):
        latest[row["rule_key"]] = row
    return [r for r in latest.values() if r["change_reason"] == "promoted"]


def _write(client, customer_id, rule, *, event, note, changed_by, now, support=None,
           approver=None, lift=None, name=None):
    now = int(time.time()) if now is None else now
    # The active state is "latest event per rule", and valid_from is whole
    # seconds. Two events on one rule in the same second would tie and the
    # outcome would depend on the order Aito returns rows in, so each event
    # is stamped strictly after the rule's previous one.
    key = rule_key(rule)
    previous = [r["valid_from"] for r in _history(client, customer_id) if r["rule_key"] == key]
    if previous and now <= max(previous):
        now = max(previous) + 1
    conditions = rule["conditions"]
    vendor = next((c["value"] for c in conditions if c["field"] == "vendor"), None)
    target = rule["target"]
    match, total = (support or {}).get("match", 0), (support or {}).get("total", 0)
    row = {
        "revision_id": f"REV-{uuid.uuid4().hex[:12]}",
        "customer_id": customer_id,
        "rule_key": key,
        "conditions": json.dumps(conditions, ensure_ascii=False),
        "target_field": target["field"],
        "target_value": str(target["value"]),
        "rule_name": name or rule_name(rule),
        # Kept for the history and drift readers, which predate generic rules.
        "vendor": vendor,
        "gl_code": str(target["value"]) if target["field"] == "gl_code" else None,
        "approver": approver,
        "support_match": int(match),
        "support_total": int(total),
        "support_ratio": round(match / total, 4) if total else 0.0,
        "lift": float(lift or 0.0),
        "valid_from": now,
        "valid_to": None,
        # `change_reason` is the event; `note` is the person's reason for it.
        # Both are the audit record, so both are stored.
        "change_reason": event,
        "note": note,
        "changed_by": changed_by,
    }
    client.insert_batch(REVISIONS_TABLE, [row])
    return row


def promote(client, customer_id: str, rule: dict, support: dict, *, reason: str,
            changed_by: str, approver: str | None = None, lift: float | None = None,
            now: int | None = None, name: str | None = None) -> dict:
    """Make `rule` active. Returns the revision written -- the audit record.

    Supersession needs no separate step: the new row becomes the latest for
    this rule_key, and the previous promotion stays in history untouched.
    """
    return _write(client, customer_id, rule, event="promoted", note=reason,
                  changed_by=changed_by, now=now, support=support,
                  approver=approver, lift=lift, name=name)


def demote(client, customer_id: str, rule: dict, *, reason: str, changed_by: str,
           now: int | None = None) -> dict:
    """Stop `rule` routing. Refuses a rule that is not active."""
    key = rule_key(rule)
    if not any(r["rule_key"] == key for r in active_rules(client, customer_id)):
        raise RuleNotActive(f"{customer_id}: no active rule for {key}")
    return _write(client, customer_id, rule, event="demoted", note=reason,
                  changed_by=changed_by, now=now)


def routed_revisions(client, customer_id: str) -> list[dict]:
    """Active revisions `check_rules` can apply: vendor -> gl_code only.

    `check_rules` matches on vendor equality alone. A multi-condition rule
    stays active in the record but is not routed: applied on vendor alone
    it would fire far more widely than it was approved for.
    """
    out = []
    for r in active_rules(client, customer_id):
        conditions = json.loads(r["conditions"])
        if (r["target_field"] == "gl_code" and len(conditions) == 1
                and conditions[0]["field"] == "vendor"):
            out.append(r)
    return out


def routing_rules(client, customer_id: str) -> list[dict]:
    """Active rules in the shape `check_rules` applies."""
    return [{"name": r["rule_name"], "vendor": r["vendor"],
             "gl_code": r["target_value"], "approver": r["approver"]}
            for r in routed_revisions(client, customer_id)]


def as_rule(mined: dict) -> dict:
    """A mined vendor -> GL rule in the generic shape."""
    return {"conditions": [{"field": "vendor", "value": mined["vendor"]}],
            "target": {"field": "gl_code", "value": mined["gl_code"]}}


def seed_promoted(client, customer_id: str, mined: list[dict], *, now: int | None = None) -> int:
    """Promote the rules that were routing before governance existed.

    So the demo routes the same invoices on day one. Idempotent: a rule
    already active with the same target is not promoted again.
    """
    active = {(r["rule_key"], r["target_value"]) for r in active_rules(client, customer_id)}
    written = 0
    for m in mined:
        rule = as_rule(m)
        if (rule_key(rule), str(m["gl_code"])) in active:
            continue
        promote(client, customer_id, rule,
                {"match": m["support_match"], "total": m["support_total"]},
                reason="seed", changed_by="seed", approver=m.get("approver"),
                lift=m.get("lift"), now=now, name=m.get("name"))
        written += 1
    return written


# Views whose content depends on which rules are active.
GOVERNED_VIEWS = ("invoices_pending", "rule_performance")


def refresh_governed_views(customer_id: str) -> None:
    """Make a promotion or demotion visible now, not at the next rebuild.

    Both views are served from precomputed payloads built on the old rule
    set. Dropping them sends the next request to the live path, which reads
    the promoted rules; bumping their versions makes every other container
    drop its pinned copy too (ADR 0023). The next precompute rebuild
    restores the fast path.
    """
    for view in GOVERNED_VIEWS:
        precompute_store.drop(precompute_store.per_customer_key(customer_id, view))
    # The live path caches its answer and its rule set. Keys mirror app.py,
    # for both API generations, since either may have served this tenant.
    for prefix in ("", "v2:"):
        for kind in ("invoices", "mined_rules", "rules_perf"):
            cache.delete(f"{kind}:{prefix}{customer_id}")
    cache_versions.bump([f"{cache_versions.PRECOMPUTE_PREFIX}{v}" for v in GOVERNED_VIEWS])
