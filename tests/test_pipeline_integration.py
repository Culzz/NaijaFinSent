"""End-to-end pipeline integration: TF-IDF sentiment + rule-based NER."""

from __future__ import annotations

from naijafinsent.inference.pipeline import AnalysisPipeline
from naijafinsent.ner.rules import RuleBasedNer
from naijafinsent.schemas import ModelRef, ProcessingStatus
from naijafinsent.sentiment.tfidf import TfidfSentimentModel

TRAIN_TEXTS = [
    "MTN Nigeria profit rises 12% on data revenue growth",
    "GTCO declares higher dividend as earnings beat expectations",
    "Dangote Cement shares rally after record profit",
    "MTN Nigeria profit falls as naira weakness squeezes margins",
    "GTCO posts loss after hefty impairment charges",
    "Dangote Cement shares slump on weak demand",
    "CBN releases quarterly statistical bulletin",
    "NGX publishes daily price list",
    "Analysts say naira weakness may pressure banks",
    "It is unclear whether the CBN will cut the MPR",
]
TRAIN_LABELS = [
    "positive", "positive", "positive",
    "negative", "negative", "negative",
    "neutral", "neutral",
    "uncertain", "uncertain",
]


def _build_pipeline() -> AnalysisPipeline:
    sentiment = TfidfSentimentModel(use_char=True)
    sentiment.fit(TRAIN_TEXTS, TRAIN_LABELS)
    ner = RuleBasedNer()
    return AnalysisPipeline(sentiment_model=sentiment, ner_model=ner)


def test_analyze_complete_with_entities_and_sentiment() -> None:
    pipeline = _build_pipeline()
    text = "MTN Nigeria profit rises 12% as CBN holds MPR at 27.5% and naira gains."
    result = pipeline.analyze(text)

    assert result.status is ProcessingStatus.COMPLETE
    assert result.sentiment is not None
    assert result.sentiment.model.task == "sentiment"
    assert len(result.sentiment.evidence) >= 1
    assert result.entities, "expected at least one entity mention"

    surfaces = {e.span.text for e in result.entities}
    assert any("MTN" in s or "CBN" in s for s in surfaces), surfaces


def test_all_entity_spans_are_valid_slices() -> None:
    pipeline = _build_pipeline()
    text = "GTCO and Dangote Cement fell as the CBN raised the MPR and oil hit $40."
    result = pipeline.analyze(text)
    for entity in result.entities:
        span = entity.span
        assert text[span.start:span.end] == span.text
        assert span.end > span.start


def test_describe_models_reports_provenance() -> None:
    pipeline = _build_pipeline()
    refs = pipeline.describe_models()
    assert all(isinstance(r, ModelRef) for r in refs)
    names = {r.name for r in refs}
    assert "tfidf-logreg" in names
    assert "rule-based-ner" in names
    tasks = {r.task for r in refs}
    assert tasks == {"sentiment", "ner"}


def test_sentiment_populated_even_without_entities() -> None:
    pipeline = _build_pipeline()
    result = pipeline.analyze("The company held its annual general meeting yesterday.")
    assert result.status is ProcessingStatus.COMPLETE
    assert result.sentiment is not None


def test_limitations_always_present() -> None:
    pipeline = _build_pipeline()
    result = pipeline.analyze("MTN Nigeria profit rises on data growth.")
    assert result.limitations, "pipeline must surface honest limitations"
    assert result.latency_ms is not None
