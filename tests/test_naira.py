"""Tests for naijafinsent.preprocessing.naira."""

from __future__ import annotations

from naijafinsent.preprocessing.naira import (
    find_money_mentions,
    normalise_unit,
    parse_money,
)
from naijafinsent.schemas import EntityType


class TestParseMoneyUnits:
    def test_naira_symbol_billion(self) -> None:
        out = parse_money("\u20a62.3bn")
        assert out["currency"] == "NGN"
        assert out["unit"] == "billion"
        assert out["value"] == 2_300_000_000.0

    def test_bare_n_no_unit_is_none(self) -> None:
        # Never infer a missing unit.
        out = parse_money("N2")
        assert out["currency"] == "NGN"
        assert out["unit"] is None
        assert out["value"] == 2.0

    def test_ngn_code(self) -> None:
        out = parse_money("NGN 1,234.5")
        assert out["currency"] == "NGN"
        assert out["unit"] is None
        assert out["value"] == 1234.5

    def test_word_million_naira(self) -> None:
        out = parse_money("40 million naira")
        assert out["currency"] == "NGN"
        assert out["unit"] == "million"
        assert out["value"] == 40_000_000.0

    def test_kobo_is_ngn_no_unit(self) -> None:
        out = parse_money("100 kobo")
        assert out["currency"] == "NGN"
        assert out["unit"] is None
        assert out["value"] == 100.0


class TestParseMoneyRanges:
    def test_symbol_range_bn(self) -> None:
        out = parse_money("\u20a62\u20133bn")
        assert out["currency"] == "NGN"
        assert out["unit"] == "billion"
        # midpoint of 2 and 3 billion
        assert out["value"] == 2_500_000_000.0

    def test_word_range_billion(self) -> None:
        out = parse_money("N2-3 billion")
        assert out["currency"] == "NGN"
        assert out["unit"] == "billion"
        assert out["value"] == 2_500_000_000.0

    def test_to_range(self) -> None:
        out = parse_money("\u20a64 to 6bn")
        assert out["unit"] == "billion"
        assert out["value"] == 5_000_000_000.0


class TestDollarDisambiguation:
    def test_dollar_price_oil_has_no_unit(self) -> None:
        out = parse_money("$40 oil")
        assert out["currency"] == "USD"
        assert out["unit"] is None
        assert out["value"] == 40.0

    def test_dollar_millions(self) -> None:
        out = parse_money("$40m")
        assert out["currency"] == "USD"
        assert out["unit"] == "million"
        assert out["value"] == 40_000_000.0

    def test_eur_and_gbp(self) -> None:
        assert parse_money("\u20ac5m")["currency"] == "EUR"
        assert parse_money("\u00a310bn")["currency"] == "GBP"


class TestNormaliseUnit:
    def test_aliases(self) -> None:
        assert normalise_unit("bn") == "billion"
        assert normalise_unit("Billion") == "billion"
        assert normalise_unit("m") == "million"
        assert normalise_unit("k") == "thousand"
        assert normalise_unit(None) is None
        assert normalise_unit("oil") is None


class TestFindMentions:
    def test_finds_money_spans(self) -> None:
        text = "MTN Nigeria lost \u20a61.2bn while CBN held MPR and oil was $40 a barrel."
        spans = find_money_mentions(text)
        surfaces = [s.text for s in spans]
        assert "\u20a61.2bn" in surfaces
        assert "$40" in surfaces
        for s in spans:
            assert s.entity_type is EntityType.MONEY
            assert text[s.start:s.end] == s.text

    def test_bare_number_not_matched(self) -> None:
        spans = find_money_mentions("The committee met 3 times in 2024.")
        assert spans == []

    def test_cbn_mpr_percent_not_money(self) -> None:
        spans = find_money_mentions("CBN held MPR at 27.5%.")
        # 27.5% is not a money mention (no currency marker).
        assert all("%" not in s.text for s in spans)

    def test_number_with_scale_and_word(self) -> None:
        spans = find_money_mentions("The bank raised 40 million naira.")
        assert any("million naira" in s.text for s in spans)

    def test_empty(self) -> None:
        assert find_money_mentions("") == []
