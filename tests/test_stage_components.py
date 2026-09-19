"""Field normalization: component names (string rules only, no alias table), weights, scale identifiers."""
from __future__ import annotations

import pytest

from src.stage.components import has_edge_whitespace, normalize_component_name, parse_weight, scale_parts
from src.vocab import WeightParseStatus


class TestComponentNames:
    def test_trim_collapse_and_casefold(self):
        assert normalize_component_name("  Chili   Con\tCarne ") == "chili con carne"

    def test_case_variants_of_one_string_share_an_identifier(self):
        assert normalize_component_name("Chili Con Carne") == normalize_component_name("Chili con carne")

    def test_trailing_whitespace_names_share_an_identifier_with_their_trimmed_form(self):
        assert normalize_component_name("CLASSIC CHICKEN GUMBO ") == normalize_component_name("classic chicken gumbo")

    def test_no_alias_table_language_variants_and_different_dishes_stay_distinct(self):
        """profiling: exports disagree by mixing language variants with genuinely different dishes. Nothing is merged."""
        pairs = [("lohkoperunoita", "baked potato"), ("kaali-porkkanaraaste", "grated cabbage"),
                 ("kalkkunaa bbq kastikkeessa", "kalkkunaa herkkusienikastikkeessa"), ("Punakaali", "Marinoitu kaalisalaatti")]
        for a, b in pairs:
            assert normalize_component_name(a) != normalize_component_name(b)

    def test_empty_or_blank_names_have_no_identifier_rather_than_an_empty_one(self):
        assert normalize_component_name("") is None and normalize_component_name("   \t ") is None

    def test_non_ascii_is_preserved(self):
        assert normalize_component_name("KÖYHÄT RITARIT") == "köyhät ritarit"

    def test_edge_whitespace_is_detected_on_the_raw_value(self):
        assert has_edge_whitespace("Broilerin koipireisi ") and has_edge_whitespace(" täysjyväohra") and not has_edge_whitespace("Rice")


class TestWeights:
    @pytest.mark.parametrize("raw, expected", [("49", 49), ("1", 1), ("2097", 2097), (" 55 ", 55), ("0", 0), ("007", 7)])
    def test_integers_parse_and_are_never_judged(self, raw, expected):
        assert parse_weight(raw) == (expected, WeightParseStatus.OK)

    @pytest.mark.parametrize("raw", ["12.5", "12,5", "1e3", "-5", "abc", "12 g", "NaN"])
    def test_non_integers_become_null_with_a_status_and_are_not_coerced(self, raw):
        assert parse_weight(raw) == (None, WeightParseStatus.NOT_INTEGER)

    def test_empty_weight_is_null_not_zero(self):
        assert parse_weight("") == (None, WeightParseStatus.EMPTY) and parse_weight("  ") == (None, WeightParseStatus.EMPTY)


class TestScaleIdentifiers:
    @pytest.mark.parametrize("scale, expected", [
        ("koti2-vasen-salaatti3", ("koti2", "vasen", "salaatti", 3)),
        ("koti2-oikea-lammin6", ("koti2", "oikea", "lammin", 6)),
        ("vege2-salaatti1", ("vege2", None, "salaatti", 1)),
        ("vege2-lammin5", ("vege2", None, "lammin", 5)),
    ])
    def test_real_patterns(self, scale, expected):
        assert scale_parts(scale) == expected

    @pytest.mark.parametrize("scale", ["mystery", "koti2-vasen-kylmä1", "a-b-c-d", ""])
    def test_unrecognised_shapes_give_nulls_not_guesses(self, scale):
        line, side, kind, pos = scale_parts(scale)
        assert kind is None and pos is None
