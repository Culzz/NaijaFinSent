"""Tests for ``naijafinsent.annotation.agreement``."""

from __future__ import annotations

import pytest

from naijafinsent.annotation.agreement import (
    AnnotatorPair,
    agreement_report,
    cohens_kappa,
    majority_vote,
    per_class_agreement,
    span_level_f1,
)
from naijafinsent.schemas import (
    AnnotationRecord,
    EntitySpan,
    EntityType,
    SentimentAnnotation,
    SentimentLabel,
)


# --------------------------------------------------------------------------
# Cohen's kappa
# --------------------------------------------------------------------------

def test_kappa_perfect_agreement_is_one() -> None:
    a = ["positive", "negative", "neutral", "uncertain", "positive"]
    b = list(a)
    assert cohens_kappa(a, b) == pytest.approx(1.0)


def test_kappa_chance_level_near_zero() -> None:
    # Independent draws with matched marginals -> kappa ~ 0.
    a = ["positive", "positive", "negative", "negative"]
    b = ["positive", "negative", "positive", "negative"]
    assert cohens_kappa(a, b) == pytest.approx(0.0, abs=1e-9)


def test_kappa_known_value_two_classes() -> None:
    # Classic worked example: agreement 0.7, pe = 0.5 -> kappa = 0.4
    a = ["p", "p", "p", "p", "p", "p", "p", "n", "n", "n"]
    b = ["p", "p", "p", "n", "n", "n", "n", "n", "n", "p"]
    # matches: 4 p/p + ... compute expected via formula in test.
    n = len(a)
    p_o = sum(1 for x, y in zip(a, b) if x == y) / n
    ca = {"p": a.count("p") / n, "n": a.count("n") / n}
    cb = {"p": b.count("p") / n, "n": b.count("n") / n}
    p_e = ca["p"] * cb["p"] + ca["n"] * cb["n"]
    expected = (p_o - p_e) / (1 - p_e)
    assert cohens_kappa(a, b) == pytest.approx(expected)


def test_kappa_degenerate_single_label() -> None:
    a = ["positive", "positive", "positive"]
    b = ["positive", "positive", "positive"]
    assert cohens_kappa(a, b) == 1.0


def test_kappa_empty_is_zero() -> None:
    assert cohens_kappa([], []) == 0.0


def test_kappa_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cohens_kappa(["a"], ["a", "b"])


def test_per_class_agreement() -> None:
    a = ["positive", "negative", "neutral", "neutral"]
    b = ["positive", "negative", "negative", "neutral"]
    per = per_class_agreement(a, b)
    assert per["neutral"]["agreement"] == pytest.approx(0.75)
    assert per["positive"]["agreement"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Span-level F1
# --------------------------------------------------------------------------

def _span(start: int, end: int, text: str, etype: EntityType) -> EntitySpan:
    return EntitySpan(start=start, end=end, text=text, entity_type=etype)


def test_span_f1_exact_perfect() -> None:
    text = "GTCO profits rose"
    spans = [_span(0, 4, "GTCO", EntityType.TICKER)]
    result = span_level_f1(spans, spans, match="exact")
    assert result["f1"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(1.0)
    assert result["recall"] == pytest.approx(1.0)


def test_span_f1_exact_vs_partial() -> None:
    text = "Dangote Cement and Dangote Sugar"
    a = [_span(0, 14, "Dangote Cement", EntityType.ORG)]
    # b guesses a overlapping-but-not-equal span of the same type
    b = [_span(0, 7, "Dangote", EntityType.ORG)]
    exact = span_level_f1(a, b, match="exact")
    partial = span_level_f1(a, b, match="partial")
    assert exact["f1"] == pytest.approx(0.0)
    assert partial["f1"] == pytest.approx(1.0)


def test_span_f1_label_mismatch_no_match() -> None:
    a = [_span(0, 4, "GTCO", EntityType.TICKER)]
    b = [_span(0, 4, "GTCO", EntityType.ORG)]
    assert span_level_f1(a, b, match="exact")["f1"] == 0.0
    assert span_level_f1(a, b, match="partial")["f1"] == 0.0


def test_span_f1_partial_precision_recall() -> None:
    a = [
        _span(0, 4, "GTCO", EntityType.TICKER),
        _span(5, 11, "profit", EntityType.EVENT_TRIGGER),
    ]
    b = [_span(0, 4, "GTCO", EntityType.TICKER)]
    result = span_level_f1(a, b, match="exact")
    assert result["precision"] == pytest.approx(1.0)
    assert result["recall"] == pytest.approx(0.5)
    assert result["f1"] == pytest.approx(2 * 1.0 * 0.5 / 1.5)


def test_span_f1_one_to_one_matching() -> None:
    # Two identical gold spans, one predicted: only one match (seqeval contract).
    a = [
        _span(0, 4, "GTCO", EntityType.TICKER),
        _span(0, 4, "GTCO", EntityType.TICKER),
    ]
    b = [_span(0, 4, "GTCO", EntityType.TICKER)]
    result = span_level_f1(a, b, match="exact")
    assert result["matched"] == 1.0
    assert result["recall"] == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Majority vote
# --------------------------------------------------------------------------

def _rec(annotator_label: str, star_ticker: bool = True) -> AnnotationRecord:
    spans = []
    if star_ticker:
        spans.append(_span(0, 4, "GTCO", EntityType.TICKER))
    return AnnotationRecord(
        item_id="item_1",
        article_id="art_1",
        split="train",
        text="GTCO profit rose",
        sentiment=SentimentAnnotation(label=SentimentLabel(annotator_label)),
        spans=spans,
    )


def test_majority_vote_sentiment() -> None:
    records = {
        "a1": _rec("positive"),
        "a2": _rec("positive"),
        "a3": _rec("negative"),
    }
    adjudicated = majority_vote(records)
    assert adjudicated.sentiment is not None
    assert adjudicated.sentiment.label.value == "positive"
    # span voted by all three -> kept
    assert len(adjudicated.spans) == 1


def test_majority_vote_min_votes_drops_minority_span() -> None:
    records = [
        _rec("positive", star_ticker=True),
        _rec("positive", star_ticker=False),
        _rec("positive", star_ticker=False),
    ]
    adjudicated = majority_vote(records, min_votes=2)
    assert adjudicated.spans == []


def test_majority_vote_single_record() -> None:
    records = {"a1": _rec("neutral")}
    adjudicated = majority_vote(records)
    assert adjudicated.sentiment is not None
    assert adjudicated.sentiment.label.value == "neutral"


# --------------------------------------------------------------------------
# Agreement report
# --------------------------------------------------------------------------

def test_agreement_report_shape() -> None:
    pairs = [
        AnnotatorPair("i1", "a1", "a2", _rec("positive"), _rec("positive")),
        AnnotatorPair("i2", "a1", "a2", _rec("negative"), _rec("neutral")),
    ]
    report = agreement_report(pairs)
    assert report["n_pairs"] == 2
    assert report["sentiment_kappa"] is not None
    assert "per_item" in report
    assert len(report["per_item"]) == 2
    assert "gates" in report
