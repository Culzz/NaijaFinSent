"""Tests for naijafinsent.preprocessing.text."""

from __future__ import annotations

from naijafinsent.preprocessing.text import (
    char_offsets_to_token_indices,
    clean_for_model,
    collapse_whitespace,
    is_likely_english,
    split_sentences,
    strip_urls,
    tokenize_words,
)


class TestTokenizer:
    def test_basic_words_and_punctuation(self) -> None:
        toks = tokenize_words("CBN raised the MPR to 27.5%, says Emefiele.")
        assert toks == ["CBN", "raised", "the", "MPR", "to", "27.5", "%", ",", "says",
                        "Emefiele", "."]

    def test_money_compound_stays_together(self) -> None:
        assert tokenize_words("Net profit hit \u20a62.3bn in Q1.") == [
            "Net", "profit", "hit", "\u20a62.3bn", "in", "Q1", "."
        ]
        assert tokenize_words("$40m") == ["$40m"]
        assert tokenize_words("N2-3bn") == ["N2-3bn"]

    def test_thousands_separator_stays_with_number(self) -> None:
        assert tokenize_words("1,234.50") == ["1,234.50"]

    def test_hyphen_and_slash_compounds(self) -> None:
        assert tokenize_words("oil & gas; x/y") == ["oil", "&", "gas", ";", "x/y"]
        assert tokenize_words("e-mail a-b") == ["e-mail", "a-b"]

    def test_empty(self) -> None:
        assert tokenize_words("") == []
        assert tokenize_words("   ") == []

    def test_deterministic(self) -> None:
        text = "GTCO up 3.2% as CBN holds MPR at 27.5%."
        assert tokenize_words(text) == tokenize_words(text)


class TestOffsetAlignment:
    def test_roundtrip_exact_offsets(self) -> None:
        text = "Guaranty Trust Bank posted \u20a62.3bn profit, up 12%."
        tokens, spans, char_to_token = char_offsets_to_token_indices(text)
        assert len(tokens) == len(spans)
        for tok, (s, e) in zip(tokens, spans):
            assert text[s:e] == tok
        assert len(char_to_token) == len(text)

    def test_char_to_token_covers_non_separators(self) -> None:
        text = "CBN raises MPR."
        tokens, spans, char_to_token = char_offsets_to_token_indices(text)
        for c, ch in enumerate(text):
            if ch.isalnum():
                idx = char_to_token[c]
                assert idx >= 0
                s, e = spans[idx]
                assert s <= c < e
            else:
                # space or punctuation may be separator (-1) or punctuation token
                assert char_to_token[c] in (-1, *range(len(tokens)))

    def test_no_gaps_between_successive_tokens(self) -> None:
        text = "a  b\tc\nd"
        tokens, spans, _ = char_offsets_to_token_indices(text)
        assert tokens == ["a", "b", "c", "d"]
        # Each token maps back exactly.
        for tok, (s, e) in zip(tokens, spans):
            assert text[s:e] == tok


class TestSentenceSplit:
    def test_basic(self) -> None:
        text = "CBN raised rates. Mr. Cardoso spoke. Profits fell 1.5% in Q1."
        sents = split_sentences(text)
        assert sents == ["CBN raised rates.", "Mr. Cardoso spoke.", "Profits fell 1.5% in Q1."]

    def test_abbreviation_not_split(self) -> None:
        sents = split_sentences("Dr. Ngozi Okonjo spoke at the summit.")
        assert len(sents) == 1

    def test_decimal_not_split(self) -> None:
        sents = split_sentences("Inflation printed at 33.9% in July.")
        assert len(sents) == 1

    def test_newline_hard_boundary(self) -> None:
        sents = split_sentences("First line\nSecond line")
        assert sents == ["First line", "Second line"]

    def test_max_len(self) -> None:
        text = "one two three four five six seven eight nine ten"
        sents = split_sentences(text, max_len=15)
        assert all(len(s) <= 15 for s in sents)
        assert "".join("".join(s.split()) for s in sents) == "".join(text.split())

    def test_empty(self) -> None:
        assert split_sentences("") == []
        assert split_sentences("   \n ") == []


class TestCleaners:
    def test_strip_urls(self) -> None:
        assert "http" not in strip_urls("see https://example.com/x now")
        assert "example.com" not in strip_urls("see www.example.com now")
        assert "@" not in strip_urls("mail me at a@b.com pls")

    def test_collapse_whitespace(self) -> None:
        assert collapse_whitespace("  a   b\t\nc ") == "a b c"

    def test_clean_for_model(self) -> None:
        out = clean_for_model("  Visit https://x.com/a  now   ")
        assert out == "Visit now"

    def test_is_likely_english(self) -> None:
        assert is_likely_english("The CBN raised the MPR to 27.5 percent.")
        assert not is_likely_english("\u042d\u0442\u043e \u0442\u0435\u0441\u0442 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c")
