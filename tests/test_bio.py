"""Tests for offset-safe BIO tagging (naijafinsent.ner.bio)."""

from __future__ import annotations

from naijafinsent.ner.bio import (
    bio_to_spans,
    spans_to_bio,
    spans_to_bio_subwords,
    token_offsets,
)
from naijafinsent.preprocessing.text import tokenize_words
from naijafinsent.schemas import EntitySpan, EntityType


def _span(text: str, surface: str, etype: EntityType) -> EntitySpan:
    start = text.index(surface)
    return EntitySpan(start=start, end=start + len(surface), text=surface, entity_type=etype)


class TestTokenOffsets:
    def test_offsets_match_surface(self) -> None:
        text = "Guaranty Trust Bank posted \u20a62.3bn profit."
        offsets = token_offsets(text, tokenize_words)
        tokens = tokenize_words(text)
        assert len(tokens) == len(offsets)
        for tok, (s, e) in zip(tokens, offsets):
            assert text[s:e] == tok


class TestBioRoundTrip:
    def test_single_org(self) -> None:
        text = "GTCO declares dividend."
        spans = [_span(text, "GTCO", EntityType.TICKER)]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        assert tokens[0] == "GTCO"
        assert tags[0] == "B-TICKER"
        assert tags[1] == "O"

        offsets = token_offsets(text, tokenize_words)
        recovered = bio_to_spans(text, tokens, tags, offsets=offsets)
        assert len(recovered) == 1
        assert recovered[0] == spans[0]

    def test_multi_word_entity(self) -> None:
        text = "Guaranty Trust Bank posted profit."
        spans = [_span(text, "Guaranty Trust Bank", EntityType.ORG)]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        assert tags[0] == "B-ORG"
        assert tags[1] == "I-ORG"
        assert tags[2] == "I-ORG"
        assert tags[3] == "O"

        recovered = bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words))
        assert recovered == spans

    def test_two_entities_of_same_type(self) -> None:
        text = "MTN Nigeria and Airtel Africa rose."
        spans = [
            _span(text, "MTN Nigeria", EntityType.ORG),
            _span(text, "Airtel Africa", EntityType.ORG),
        ]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        recovered = bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words))
        assert recovered == spans

    def test_overlapping_types_do_not_crash(self) -> None:
        text = "CBN governor spoke."
        spans = [_span(text, "CBN", EntityType.REGULATOR)]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        recovered = bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words))
        assert recovered[0].entity_type is EntityType.REGULATOR

    def test_no_spans_all_o(self) -> None:
        text = "Nothing here at all."
        tokens, tags = spans_to_bio(text, [], tokenize_words)
        assert set(tags) == {"O"}
        assert bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words)) == []

    def test_money_span_with_symbol(self) -> None:
        text = "Profit hit \u20a62.3bn in Q1."
        spans = [_span(text, "\u20a62.3bn", EntityType.MONEY)]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        assert "B-MONEY" in tags
        recovered = bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words))
        assert recovered == spans
        assert text[recovered[0].start:recovered[0].end] == "\u20a62.3bn"

    def test_exact_offsets_preserved(self) -> None:
        text = "The CBN and SEC acted; GTCO fell 3%."
        spans = [
            _span(text, "CBN", EntityType.REGULATOR),
            _span(text, "SEC", EntityType.REGULATOR),
            _span(text, "GTCO", EntityType.TICKER),
        ]
        tokens, tags = spans_to_bio(text, spans, tokenize_words)
        recovered = bio_to_spans(text, tokens, tags, offsets=token_offsets(text, tokenize_words))
        for original, got in zip(spans, recovered):
            assert got.start == original.start
            assert got.end == original.end
            assert got.text == original.text


class TestSubwordBio:
    def test_continuation_gets_i_tag(self) -> None:
        # Simulate subword offsets for word "Nigeria" split into "Niger" + "ia".
        text = "MTN Nigeria"
        offsets = [(0, 0), (0, 3), (4, 9), (9, 11), (0, 0)]  # [CLS] MTN Niger ia [SEP]
        spans = [EntitySpan(start=0, end=3, text="MTN", entity_type=EntityType.ORG),
                 EntitySpan(start=4, end=11, text="Nigeria", entity_type=EntityType.ORG)]
        special = [s == 0 and e == 0 for (s, e) in offsets]
        tags = spans_to_bio_subwords(offsets, spans, special_mask=special)
        assert tags[0] == "O"           # [CLS]
        assert tags[1] == "B-ORG"       # MTN
        assert tags[2] == "B-ORG"       # Niger
        assert tags[3] == "I-ORG"       # ia
        assert tags[4] == "O"           # [SEP]
