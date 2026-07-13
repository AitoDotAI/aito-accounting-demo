"""Tests for the Aito v2 client's pure helpers.

The one piece of real logic (vs. thin HTTP) in `AitoV2Client` is parsing
v2's stringified `$patterns` proposition back into the v1 dict shape, so
the existing rule-mining code can consume v2 responses unchanged. These
tests pin that parser against the exact (non-JSON) strings v2 returns.
"""

from src.aito_v2_client import parse_pattern_proposition


class TestParsePatternProposition:
    def test_single_clause_becomes_has_dict(self):
        # A `condition` like `{ gl_code:5300 }` → `{gl_code: {$has: "5300"}}`.
        assert parse_pattern_proposition("{ gl_code:5300 }") == {
            "gl_code": {"$has": "5300"}
        }

    def test_and_conjunction_becomes_and_list(self):
        text = '{ "$and" : [ { category:supplies }, { vendor:EEE Energy Oy } ] }'
        assert parse_pattern_proposition(text) == {
            "$and": [
                {"category": {"$has": "supplies"}},
                {"vendor": {"$has": "EEE Energy Oy"}},
            ]
        }

    def test_values_may_contain_spaces(self):
        # Vendor names are unquoted yet contain spaces — the value runs to
        # the closing brace.
        assert parse_pattern_proposition("{ vendor:Investra Management Oy }") == {
            "vendor": {"$has": "Investra Management Oy"}
        }

    def test_non_breaking_space_separator_is_handled(self):
        # v2 emits a NBSP (\xa0) after the `[` in some responses.
        text = '{ "$and" : [\xa0{ vendor:Acme Oy }, { category:insurance } ] }'
        assert parse_pattern_proposition(text) == {
            "$and": [
                {"vendor": {"$has": "Acme Oy"}},
                {"category": {"$has": "insurance"}},
            ]
        }

    def test_three_clause_conjunction(self):
        text = ('{ "$and" : [ { vendor:Dottoressa Oy }, { category:consulting }, '
                "{ amount_band:medium } ] }")
        parsed = parse_pattern_proposition(text)
        assert parsed == {
            "$and": [
                {"vendor": {"$has": "Dottoressa Oy"}},
                {"category": {"$has": "consulting"}},
                {"amount_band": {"$has": "medium"}},
            ]
        }
