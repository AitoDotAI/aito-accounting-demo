"""Mining proposes, promotion activates. See ADR 0025.

Before this, Invoice Processing routed on every mined rule the moment its
support crossed 95% -- no human saw it first, although three pages of
copy said one did. Now a rule routes only while its latest revision is a
promotion. Revisions are append-only events: promoting, demoting and
superseding each ADD a row, so the table is the audit trail and nothing
in it is ever rewritten.
"""

import pytest

from src import rule_governance as rg


class MemoryStore:
    """rule_revisions in memory: search by customer, append rows."""

    def __init__(self):
        self.rows: list[dict] = []

    def search(self, table, where, limit=10):
        assert table == "rule_revisions"
        hits = [r for r in self.rows if all(r.get(k) == v for k, v in where.items())]
        return {"total": len(hits), "hits": hits[:limit]}

    def insert_batch(self, name, rows, batch_size=1000):
        assert name == "rule_revisions"
        self.rows.extend(dict(r) for r in rows)
        return len(rows)


EUROPRESS = {"conditions": [{"field": "vendor", "value": "Europress Group Oy"}],
             "target": {"field": "gl_code", "value": "5100"}}
SUPPORT = {"match": 505, "total": 513}


@pytest.fixture
def store():
    return MemoryStore()


def _promote(store, rule=EUROPRESS, t=100, approver="CUST-0007-EMP-0002"):
    return rg.promote(store, "CUST-0007", rule, SUPPORT, approver=approver,
                      reason="reviewed", changed_by="Antti", now=t)


class TestMiningDoesNotRoute:
    def test_a_tenant_with_no_promotions_has_no_active_rules(self, store):
        assert rg.active_rules(store, "CUST-0007") == []


class TestPromote:
    def test_promoting_makes_the_rule_active(self, store):
        _promote(store)

        active = rg.active_rules(store, "CUST-0007")
        assert [(r["target_field"], r["target_value"]) for r in active] == [("gl_code", "5100")]

    def test_the_revision_is_the_audit_record(self, store):
        row = _promote(store)

        assert row["change_reason"] == "promoted"
        assert row["changed_by"] == "Antti"
        assert store.rows[0]["note"] == "reviewed", "the reason must be STORED, not only returned"
        assert (row["support_match"], row["support_total"]) == (505, 513)
        assert row["valid_from"] == 100

    def test_promoting_a_new_target_for_the_same_conditions_supersedes(self, store):
        """Only one open rule per (conditions, target field)."""
        _promote(store, t=100)
        _promote(store, {**EUROPRESS, "target": {"field": "gl_code", "value": "5400"}}, t=200)

        active = rg.active_rules(store, "CUST-0007")
        assert [r["target_value"] for r in active] == ["5400"]

    def test_history_is_append_only(self, store):
        _promote(store, t=100)
        _promote(store, {**EUROPRESS, "target": {"field": "gl_code", "value": "5400"}}, t=200)

        assert [r["change_reason"] for r in store.rows] == ["promoted", "promoted"]
        assert store.rows[0]["target_value"] == "5100", "earlier revision must not be rewritten"

    def test_rules_are_tenant_scoped(self, store):
        _promote(store)

        assert rg.active_rules(store, "CUST-0000") == []


class TestDemote:
    def test_demoting_removes_the_rule_from_the_active_set(self, store):
        _promote(store, t=100)

        rg.demote(store, "CUST-0007", EUROPRESS, reason="drifted", changed_by="Antti", now=200)

        assert rg.active_rules(store, "CUST-0007") == []
        assert [r["change_reason"] for r in store.rows] == ["promoted", "demoted"]

    def test_demoting_an_inactive_rule_is_refused(self, store):
        with pytest.raises(rg.RuleNotActive):
            rg.demote(store, "CUST-0007", EUROPRESS, reason="x", changed_by="Antti", now=1)


class TestRoutingShape:
    def test_active_vendor_rules_become_check_rules_entries(self, store):
        _promote(store)

        routing = rg.routing_rules(store, "CUST-0007")

        assert routing == [{"name": "Europress Group Oy → GL 5100", "vendor": "Europress Group Oy",
                            "gl_code": "5100", "approver": "CUST-0007-EMP-0002"}]

    def test_rules_check_rules_cannot_apply_are_not_offered_to_it(self, store):
        """check_rules matches on vendor alone; a multi-condition rule would
        be applied too broadly, so it is active but not routed."""
        multi = {"conditions": [{"field": "category", "value": "it_equipment"},
                                {"field": "amount_band", "value": "large"}],
                 "target": {"field": "gl_code", "value": "1600"}}
        _promote(store, multi)

        assert rg.routing_rules(store, "CUST-0007") == []


class TestSeed:
    def test_seeding_promotes_the_mined_set(self, store):
        mined = [{"name": "Europress Group Oy → GL 5100", "vendor": "Europress Group Oy",
                  "gl_code": "5100", "approver": "CUST-0007-EMP-0002",
                  "support_match": 505, "support_total": 513, "support_ratio": 0.984, "lift": 3.1}]

        rg.seed_promoted(store, "CUST-0007", mined, now=100)

        assert rg.routing_rules(store, "CUST-0007") == [
            {k: mined[0][k] for k in ("name", "vendor", "gl_code", "approver")}]

    def test_seeding_twice_does_not_duplicate(self, store):
        mined = [{"name": "Europress Group Oy → GL 5100", "vendor": "Europress Group Oy",
                  "gl_code": "5100", "approver": "CUST-0007-EMP-0002",
                  "support_match": 505, "support_total": 513, "support_ratio": 0.984, "lift": 3.1}]

        rg.seed_promoted(store, "CUST-0007", mined, now=100)
        rg.seed_promoted(store, "CUST-0007", mined, now=200)

        assert len(store.rows) == 1


class TestAPromotionIsVisibleImmediately:
    """Routing views are served from precomputed payloads built on the OLD
    rule set. Without dropping them, a promotion would change nothing on
    screen until the next precompute rebuild."""

    def test_the_tenants_governed_views_are_dropped_and_versions_bumped(self, monkeypatch):
        dropped, bumped, cleared = [], [], []
        monkeypatch.setattr(rg.precompute_store, "drop", lambda name: dropped.append(name))
        monkeypatch.setattr(rg.cache_versions, "bump", lambda scopes: bumped.extend(scopes))
        monkeypatch.setattr(rg.cache, "delete", lambda key: cleared.append(key))

        rg.refresh_governed_views("CUST-0007")

        assert set(dropped) == {"cust:CUST-0007:invoices_pending",
                                "cust:CUST-0007:rule_performance"}
        assert set(bumped) == {"precompute:invoices_pending", "precompute:rule_performance"}
        assert any("CUST-0007" in k for k in cleared)


def test_a_promoted_rule_is_named_like_a_mined_one():
    """The name appears in every routed invoice's explanation, so a rule
    must read the same before and after it is promoted."""
    assert rg.rule_name(EUROPRESS) == "Europress Group Oy → GL 5100"


def test_events_in_the_same_second_keep_their_order(store):
    """valid_from is whole seconds. A demote and a re-promote in one second
    must not tie, or the active state depends on the order Aito returns."""
    _promote(store, t=100)
    rg.demote(store, "CUST-0007", EUROPRESS, reason="x", changed_by="Antti", now=100)
    _promote(store, t=100)
    store.rows.reverse()  # the engine promises no order

    assert [r["target_value"] for r in rg.active_rules(store, "CUST-0007")] == ["5100"]
    assert len({r["valid_from"] for r in store.rows}) == 3


MINED = [{"name": "Europress Group Oy → GL 5100", "vendor": "Europress Group Oy",
          "gl_code": "5100", "approver": "CUST-0007-EMP-0002",
          "support_match": 505, "support_total": 513, "support_ratio": 0.984, "lift": 3.1}]
OTHER = {"conditions": [{"field": "vendor", "value": "Kotimekko Oy"}],
         "target": {"field": "gl_code", "value": "5300"}}


class TestTheDemoRestoresItself:
    """Demote is public. One visitor must not strip the routed rules for
    every later visitor until a person notices -- the seeded state comes
    back on its own, and on request."""

    def _state(self, store):
        return sorted((r["vendor"], r["target_value"]) for r in rg.active_rules(store, "CUST-0007"))

    def test_a_demoted_seed_rule_is_restored(self, store):
        rg.seed_promoted(store, "CUST-0007", MINED, now=100)
        rg.demote(store, "CUST-0007", EUROPRESS, reason="x", changed_by="demo user", now=200)

        changed = rg.restore_seed(store, "CUST-0007", now=300)

        assert self._state(store) == [("Europress Group Oy", "5100")]
        assert changed == 1

    def test_a_superseded_seed_rule_is_restored(self, store):
        rg.seed_promoted(store, "CUST-0007", MINED, now=100)
        _promote(store, {**EUROPRESS, "target": {"field": "gl_code", "value": "5400"}}, t=200)

        rg.restore_seed(store, "CUST-0007", now=300)

        assert self._state(store) == [("Europress Group Oy", "5100")]

    def test_a_visitor_promoted_rule_is_demoted(self, store):
        rg.seed_promoted(store, "CUST-0007", MINED, now=100)
        rg.promote(store, "CUST-0007", OTHER, {"match": 9, "total": 9},
                   reason="x", changed_by="demo user", now=200)

        rg.restore_seed(store, "CUST-0007", now=300)

        assert self._state(store) == [("Europress Group Oy", "5100")]

    def test_restoring_the_seeded_state_is_a_no_op(self, store):
        rg.seed_promoted(store, "CUST-0007", MINED, now=100)
        before = len(store.rows)

        assert rg.restore_seed(store, "CUST-0007", now=300) == 0
        assert len(store.rows) == before

    def test_restore_is_recorded_not_rewritten(self, store):
        rg.seed_promoted(store, "CUST-0007", MINED, now=100)
        rg.demote(store, "CUST-0007", EUROPRESS, reason="x", changed_by="demo user", now=200)

        rg.restore_seed(store, "CUST-0007", now=300, changed_by="auto-restore")

        assert [(r["change_reason"], r["changed_by"]) for r in store.rows] == [
            ("promoted", "seed"), ("demoted", "demo user"), ("promoted", "auto-restore")]


def test_the_hourly_pass_restores_only_tenants_a_visitor_touched(store, monkeypatch):
    from src import rule_restore
    refreshed = []
    monkeypatch.setattr(rg, "refresh_governed_views", lambda cid: refreshed.append(cid))
    rg.seed_promoted(store, "CUST-0007", MINED, now=100)
    rg.seed_promoted(store, "CUST-0000", MINED, now=100)
    rg.demote(store, "CUST-0007", EUROPRESS, reason="x", changed_by="demo user", now=200)

    changed = rule_restore.restore_once(store)

    assert changed == {"CUST-0007": 1}
    assert refreshed == ["CUST-0007"]


def test_the_restore_timer_can_be_disabled(monkeypatch):
    from src import rule_restore
    monkeypatch.setenv("RULES_RESTORE_SECONDS", "0")

    assert rule_restore.start(None) is False
