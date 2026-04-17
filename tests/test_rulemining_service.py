"""Tests for the rule mining service.

Tests verify pattern extraction from _relate responses, support ratio
classification, and candidate sorting. These double as documentation
for how Aito _relate responses map to human-readable rule candidates.
"""

import pytest

from src.rulemining_service import (
    RuleCandidate,
    classify_strength,
    extract_candidates_from_relate,
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

    def test_zero_is_weak(self):
        assert classify_strength(0.0) == "weak"


class TestExtractCandidates:
    def _make_relate_hit(self, gl_code, f_on_condition, f_condition, n=230, lift=5.0):
        return {
            "related": {"gl_code": {"$has": gl_code}},
            "condition": {"category": {"$has": "telecom"}},
            "lift": lift,
            "fs": {
                "f": f_on_condition + 10,
                "fOnCondition": f_on_condition,
                "fOnNotCondition": 10,
                "fCondition": f_condition,
                "n": n,
            },
            "ps": {
                "p": 0.1,
                "pOnCondition": f_on_condition / max(f_condition, 1),
                "pOnNotCondition": 0.05,
                "pCondition": f_condition / max(n, 1),
            },
        }

    def test_extracts_strong_pattern_from_relate(self):
        """17/17 telecom → GL 6200 should be a strong candidate."""
        result = {
            "offset": 0,
            "total": 1,
            "hits": [self._make_relate_hit("6200", 17, 17, 230, 10.7)],
        }

        candidates = extract_candidates_from_relate("category", "telecom", result)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.condition_field == "category"
        assert c.condition_value == "telecom"
        assert c.target_value == "6200"
        assert c.support_match == 17
        assert c.support_total == 17
        assert c.strength == "strong"
        assert c.support_ratio == 1.0

    def test_extracts_review_pattern(self):
        """33/34 food_bev → GL 4100 should be review (97%)."""
        result = {
            "offset": 0,
            "total": 1,
            "hits": [self._make_relate_hit("4100", 33, 34, 230, 6.0)],
        }

        candidates = extract_candidates_from_relate("category", "food_bev", result)

        assert len(candidates) == 1
        assert candidates[0].strength == "strong"  # 33/34 = 97%
        assert candidates[0].support_ratio == pytest.approx(0.97, abs=0.01)

    def test_skips_low_support_patterns(self):
        """Patterns with fewer than MIN_SUPPORT matches are ignored."""
        result = {
            "offset": 0,
            "total": 1,
            "hits": [self._make_relate_hit("4400", 2, 5, 230, 1.0)],
        }

        candidates = extract_candidates_from_relate("vendor", "Rare Corp", result)

        assert len(candidates) == 0

    def test_only_takes_top_hit(self):
        """Should only extract the first (highest-lift) hit per condition."""
        result = {
            "offset": 0,
            "total": 2,
            "hits": [
                self._make_relate_hit("6200", 17, 17, 230, 10.7),
                self._make_relate_hit("4400", 5, 17, 230, 0.5),
            ],
        }

        candidates = extract_candidates_from_relate("category", "telecom", result)

        assert len(candidates) == 1
        assert candidates[0].target_value == "6200"

    def test_empty_hits_returns_empty(self):
        result = {"offset": 0, "total": 0, "hits": []}

        candidates = extract_candidates_from_relate("vendor", "Nobody", result)

        assert candidates == []


class TestRuleCandidate:
    def test_pattern_display(self):
        c = RuleCandidate(
            condition_field="category",
            condition_value="telecom",
            target_field="gl_code",
            target_value="6200",
            target_label="Telecom",
            support_match=17,
            support_total=17,
            coverage=0.074,
            lift=10.7,
            strength="strong",
        )

        assert c.pattern_display == 'category="telecom"'
        assert c.target_display == "GL 6200 (Telecom)"

    def test_to_dict_includes_all_fields(self):
        c = RuleCandidate(
            condition_field="vendor",
            condition_value="Kesko Oyj",
            target_field="gl_code",
            target_value="4400",
            target_label="Supplies",
            support_match=18,
            support_total=18,
            coverage=0.078,
            lift=6.5,
            strength="strong",
        )
        d = c.to_dict()

        assert d["pattern"] == 'vendor="Kesko Oyj"'
        assert d["target"] == "GL 4400 (Supplies)"
        assert d["support"] == "18/18"
        assert d["support_ratio"] == 1.0
        assert d["coverage"] == 7.8
        assert d["strength"] == "strong"

    def test_support_ratio_zero_division(self):
        c = RuleCandidate("f", "v", "t", "x", "X", 0, 0, 0.0, 0.0, "weak")
        assert c.support_ratio == 0.0
