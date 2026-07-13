"""Tests for the Aito v2 client's pure helpers.

The one piece of real logic (vs. thin HTTP) in `AitoV2Client` is parsing
v2's stringified `$patterns` proposition back into the v1 dict shape, so
the existing rule-mining code can consume v2 responses unchanged. These
tests pin that parser against the exact (non-JSON) strings v2 returns.
"""

from src.aito_v2_client import AitoV2Client, parse_pattern_proposition


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


class _FakeSearchClient(AitoV2Client):
    """AitoV2Client with `search` stubbed against an in-memory table, so the
    pure recompute logic in `relate_features` can be tested without network.
    """

    def __init__(self, rows):
        self._rows = rows  # deliberately skip the HTTP client setup

    def search(self, table, where, limit=10):
        matched = [r for r in self._rows
                   if all(r.get(k) == v for k, v in where.items())]
        return {"total": len(matched), "hits": matched[:limit] if limit else []}


class TestRelateFeaturesRecompute:
    """`relate_features` must recompute exact fs and a v1-matching lift
    (agree_ratio / base_rate) over the UNCONDITIONED population — including
    the exception values that never hit the target.
    """

    def _rows(self):
        # Population vendor="X": 5 large (4 hit 1600), 3 medium (0 hit 1600).
        rows = []
        rows += [{"vendor": "X", "amount_band": "large", "gl_code": "1600"}] * 4
        rows += [{"vendor": "X", "amount_band": "large", "gl_code": "4400"}] * 1
        rows += [{"vendor": "X", "amount_band": "medium", "gl_code": "4400"}] * 3
        return rows

    def test_recomputes_fs_and_lift_including_the_exception(self):
        client = _FakeSearchClient(self._rows())
        out = client.relate_features(
            "invoices", {"vendor": "X"}, {"gl_code": "1600"}, ["amount_band"]
        )
        by_value = {h["related"]["amount_band"]["$has"]: h for h in out["hits"]}
        # base_rate = 4/8 = 0.5
        large = by_value["large"]
        assert large["fs"] == {"f": 5, "fOnCondition": 4}
        assert large["lift"] == (4 / 5) / 0.5  # 1.6 — agreement driver

        # The exception value (never hits the target) must still appear.
        medium = by_value["medium"]
        assert medium["fs"] == {"f": 3, "fOnCondition": 0}
        assert medium["lift"] == 0.0
