"""Tests for the rule mining service.

Rule mining is two stages (ADR 0014), now across multiple target fields:

  1. `discover_conjunctions` pulls candidate input-only conjunctions out of
     a `$patterns` response — discovery only, since `$patterns`' `fs` are
     estimates.
  2. `build_candidate` turns exact `_search` counts into the rule's
     support/coverage/lift, so the displayed "X of Y" matches the
     drill-down.

Rules are mined for each *output* field (gl_code, approver) from
inputs-only clauses — never conditioning on another output (no leakage).
"""

import pytest

from src.rulemining_service import (
    RuleCandidate,
    RuleClause,
    build_candidate,
    classify_strength,
    discover_conjunctions,
    interpret_diagnosis,
    parse_conjunction,
    target_value_label,
)


class TestClassifyStrength:
    def test_perfect_ratio_is_strong(self):
        assert classify_strength(1.0) == "strong"

    def test_95_percent_is_strong(self):
        assert classify_strength(0.95) == "strong"

    def test_94_percent_is_review(self):
        assert classify_strength(0.94) == "review"

    def test_75_percent_is_review(self):
        assert classify_strength(0.75) == "review"

    def test_74_percent_is_weak(self):
        assert classify_strength(0.74) == "weak"


class TestTargetValueLabel:
    def test_gl_code_maps_to_label(self):
        assert target_value_label("gl_code", "5400") == "Professional Services"
        assert target_value_label("gl_code", "1600") == "Capital Equipment"

    def test_unknown_gl_falls_back_to_code(self):
        assert target_value_label("gl_code", "9999") == "9999"

    def test_approver_is_its_own_label(self):
        assert target_value_label("approver", "Liisa Virtanen") == "Liisa Virtanen"


class TestParseConjunction:
    def test_single_feature_becomes_one_clause(self):
        assert parse_conjunction({"category": {"$has": "insurance"}}) == [
            RuleClause("category", "insurance")
        ]

    def test_and_conjunction_becomes_multiple_clauses(self):
        related = {"$and": [
            {"category": {"$has": "it_equipment"}},
            {"amount_band": {"$has": "large"}},
        ]}
        assert parse_conjunction(related) == [
            RuleClause("category", "it_equipment"),
            RuleClause("amount_band", "large"),
        ]


class TestDiscoverConjunctions:
    def _hit(self, related, *, lift=10.0, condition=None):
        return {
            "related": related,
            "condition": condition or {"gl_code": {"$has": "1600"}},
            "lift": lift,
        }

    def test_discovers_input_conjunction(self):
        related = {"$and": [
            {"category": {"$has": "it_equipment"}},
            {"amount_band": {"$has": "large"}},
        ]}
        out = discover_conjunctions("gl_code", "1600", {"hits": [self._hit(related)]})
        assert out == [[RuleClause("category", "it_equipment"), RuleClause("amount_band", "large")]]

    def test_drops_negative_estimated_lift(self):
        result = {"hits": [
            self._hit({"category": {"$has": "supplies"}}, lift=0.1),
            self._hit({"category": {"$has": "it_equipment"}}, lift=8.0),
        ]}
        out = discover_conjunctions("gl_code", "1600", result)
        assert out == [[RuleClause("category", "it_equipment")]]

    def test_deduplicates(self):
        related = {"category": {"$has": "it_equipment"}}
        result = {"hits": [self._hit(related), self._hit(related)]}
        assert len(discover_conjunctions("gl_code", "1600", result)) == 1

    def test_works_for_approver_target(self):
        """Discovery is target-agnostic — condition must match the target field."""
        related = {"$and": [
            {"category": {"$has": "consulting"}},
            {"amount_band": {"$has": "large"}},
        ]}
        hit = self._hit(related, condition={"approver": {"$has": "Markku Heikkinen"}})
        out = discover_conjunctions("approver", "Markku Heikkinen", {"hits": [hit]})
        assert out == [[RuleClause("category", "consulting"), RuleClause("amount_band", "large")]]

    def test_raises_when_condition_is_not_the_target_field(self):
        bad = self._hit({"category": {"$has": "x"}}, condition={"customer_id": {"$has": "C"}})
        with pytest.raises(ValueError, match="wrong target"):
            discover_conjunctions("gl_code", "1600", {"hits": [bad]})

    def test_empty_hits(self):
        assert discover_conjunctions("gl_code", "1600", {"hits": []}) == []


class TestBuildCandidate:
    def test_gl_target_exact_counts(self):
        """The capitalization rule: it_equipment+large mostly → 1600."""
        c = build_candidate(
            [RuleClause("category", "it_equipment"), RuleClause("amount_band", "large")],
            "gl_code", "1600",
            rule_total=1261, rule_match=1251, target_total=12222, n=16000,
        )
        assert c.target_field == "gl_code"
        assert c.support_ratio == pytest.approx(1251 / 1261, abs=0.001)
        assert c.coverage == pytest.approx(1251 / 12222, abs=0.001)
        # lift = precision / (target_total/n)
        assert c.lift == pytest.approx((1251 / 1261) / (12222 / 16000), abs=0.02)
        assert c.strength == "strong"
        assert c.target_display == "GL 1600 (Capital Equipment)"

    def test_approver_target_display_is_the_name(self):
        c = build_candidate(
            [RuleClause("amount_band", "large")],
            "approver", "Markku Heikkinen",
            rule_total=600, rule_match=590, target_total=900, n=16000,
        )
        assert c.target_field == "approver"
        assert c.target_label == "Markku Heikkinen"
        assert c.target_display == "Markku Heikkinen"
        assert c.support_ratio == pytest.approx(590 / 600, abs=0.001)

    def test_zero_division_guards(self):
        c = build_candidate([RuleClause("category", "x")], "gl_code", "1600", 0, 0, 0, 0)
        assert c.support_ratio == 0.0 and c.coverage == 0.0 and c.lift == 0.0


class TestRuleCandidate:
    def _candidate(self, **overrides):
        defaults = dict(
            clauses=[RuleClause("category", "it_equipment"), RuleClause("amount_band", "large")],
            target_field="gl_code", target_value="1600", target_label="Capital Equipment",
            rule_match=1251, rule_total=1261, target_total=12222, n=16000,
            lift=1.6, strength="strong",
        )
        defaults.update(overrides)
        return RuleCandidate(**defaults)

    def test_to_dict_includes_target_field_and_clauses(self):
        d = self._candidate().to_dict()
        assert d["pattern"] == 'category="it_equipment" AND amount_band="large"'
        assert d["clauses"] == [
            {"field": "category", "value": "it_equipment"},
            {"field": "amount_band", "value": "large"},
        ]
        assert d["target_field"] == "gl_code"
        assert d["target"] == "GL 1600 (Capital Equipment)"
        assert d["support"] == "1251/1261"
        assert d["strength"] == "strong"

    def test_single_feature_renders_without_and(self):
        c = self._candidate(clauses=[RuleClause("category", "insurance")])
        assert c.pattern_display == 'category="insurance"'


class TestInterpretDiagnosis:
    def _hit(self, field, value, *, lift, f, f_on):
        return {"related": {field: {"$has": value}}, "lift": lift,
                "fs": {"f": f, "fOnCondition": f_on}}

    def test_structural_exceptions_suggest_a_refinement(self):
        """K. Itäluoma case: exceptions are amount_band=medium; agreements
        are amount_band=large → suggest adding amount_band=large."""
        result = {"hits": [
            self._hit("amount_band", "large", lift=1.08, f=327, f_on=322),
            self._hit("vendor_country", "FI", lift=1.0, f=353, f_on=322),
            self._hit("amount_band", "medium", lift=0.02, f=26, f_on=0),
        ]}

        d = interpret_diagnosis(["amount_band", "vendor_country"], result)

        assert d["explains_exceptions"][0]["field"] == "amount_band"
        assert d["explains_exceptions"][0]["value"] == "medium"
        assert d["explains_exceptions"][0]["agree"] == 0
        assert d["suggestion"]["field"] == "amount_band"
        assert d["suggestion"]["value"] == "large"
        assert "large" in d["suggestion"]["text"]

    def test_random_exceptions_yield_no_suggestion(self):
        """Dottoressa case: all lifts ≈ 1 → exceptions are noise."""
        result = {"hits": [
            self._hit("amount_band", "medium", lift=1.0, f=778, f_on=764),
            self._hit("vendor_country", "FI", lift=1.0, f=831, f_on=815),
            self._hit("amount_band", "large", lift=0.98, f=53, f_on=51),
        ]}

        d = interpret_diagnosis(["amount_band", "vendor_country"], result)

        assert d["explains_exceptions"] == []
        assert d["suggestion"] is None

    def test_low_support_feature_values_are_dropped(self):
        result = {"hits": [self._hit("amount_band", "small", lift=0.1, f=2, f_on=0)]}
        d = interpret_diagnosis(["amount_band"], result)
        assert d["explains_exceptions"] == []
