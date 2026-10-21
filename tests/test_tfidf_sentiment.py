"""Tests for the TF-IDF sentiment baseline."""

from __future__ import annotations

import pytest

from naijafinsent.constants import SENTIMENT_LABELS
from naijafinsent.schemas import SentimentLabel, SentimentPrediction
from naijafinsent.sentiment.tfidf import TfidfSentimentModel, TfidfSvmSentimentModel

# --- tiny synthetic Nigerian financial corpus --------------------------------
# 5 examples per class, deliberately separable so an honest baseline beats
# majority class; kept inline so the test has no data dependency.
TRAIN_TEXTS: list[str] = [
    # positive
    "MTN Nigeria profit rises 12% on strong data revenue growth",
    "GTCO declares higher dividend as earnings beat expectations",
    "Dangote Cement shares rally after record quarterly profit",
    "Banks post robust earnings as loan growth accelerates",
    "Naira stabilises and stocks gain on improved FX inflows",
    # negative
    "MTN Nigeria profit falls as naira weakness squeezes margins",
    "GTCO posts loss after hefty impairment charges",
    "Dangote Cement shares slump on weak demand and rising costs",
    "Banks face rising bad loans as borrowers struggle to repay",
    "Naira plunges and stocks tumble on FX scarcity concerns",
    # neutral
    "CBN releases its quarterly statistical bulletin for the period",
    "NGX publishes the daily price list for listed equities",
    "The company held its annual general meeting in Lagos yesterday",
    "SEC issued a circular outlining new reporting requirements",
    "The bank appointed a new non-executive director to its board",
    # uncertain
    "Analysts say naira weakness may pressure banks next year",
    "It is unclear whether the CBN will cut the MPR at its next meeting",
    "The outlook for cement demand remains uncertain amid FX volatility",
    "Profit could decline if fuel subsidy removal bites further",
    "Whether the merger completes depends on regulatory approval",
]
TRAIN_LABELS: list[str] = (
    ["positive"] * 5 + ["negative"] * 5 + ["neutral"] * 5 + ["uncertain"] * 5
)

TEST_TEXTS: list[str] = [
    "MTN Nigeria profit rises strongly on data growth",
    "GTCO slumps to a loss amid impairment charges",
    "The CBN published its statistical bulletin",
    "The outlook remains uncertain as FX pressure persists",
]
TEST_LABELS: list[str] = ["positive", "negative", "neutral", "uncertain"]


def test_beats_majority_class() -> None:
    from collections import Counter

    majority = Counter(TRAIN_LABELS).most_common(1)[0]
    majority_label = majority[0]
    majority_acc = sum(1 for y in TEST_LABELS if y == majority_label) / len(TEST_LABELS)

    model = TfidfSentimentModel(use_char=True)
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    preds = [model.predict(t).label.value for t in TEST_TEXTS]
    acc = sum(1 for a, b in zip(preds, TEST_LABELS) if a == b) / len(TEST_LABELS)

    assert acc >= majority_acc, (acc, majority_acc, preds)
    assert acc >= 0.75, preds


def test_predict_returns_valid_sentiment_prediction() -> None:
    model = TfidfSentimentModel(use_char=True)
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    pred = model.predict("MTN Nigeria profit rises strongly on data growth")
    assert isinstance(pred, SentimentPrediction)
    assert pred.label in {SentimentLabel(l) for l in SENTIMENT_LABELS}
    assert 0.0 <= pred.confidence <= 1.0
    assert len(pred.evidence) >= 1
    assert pred.model.name == "tfidf-logreg"
    assert pred.model.task == "sentiment"
    # Every evidence span must be a real slice of the text.
    text = "MTN Nigeria profit rises strongly on data growth"
    for span in pred.evidence:
        assert text[span.start:span.end] == span.text


def test_probabilities_valid_distribution() -> None:
    model = TfidfSentimentModel()
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    probs = model.predict_proba("Naira weakness may pressure banks")
    assert set(probs) <= set(SENTIMENT_LABELS)
    assert all(0.0 <= v <= 1.0 for v in probs.values())
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_top_features() -> None:
    model = TfidfSentimentModel()
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    feats = model.top_features(5)
    assert set(feats) <= set(SENTIMENT_LABELS)
    assert all(len(v) <= 5 for v in feats.values())


def test_save_load_roundtrip(tmp_path) -> None:
    model = TfidfSentimentModel()
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    path = tmp_path / "model.joblib"
    model.save(path)
    loaded = TfidfSentimentModel.load(path)
    a = model.predict("MTN Nigeria profit rises strongly")
    b = loaded.predict("MTN Nigeria profit rises strongly")
    assert a.label == b.label
    assert a.model.name == b.model.name


def test_svm_variant_produces_probabilities() -> None:
    model = TfidfSvmSentimentModel(cv=2)
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    pred = model.predict("GTCO slumps to a loss amid impairment charges")
    assert isinstance(pred, SentimentPrediction)
    assert pred.model.name == "tfidf-linearsvm"
    assert len(pred.evidence) >= 1


def test_predict_batch() -> None:
    model = TfidfSentimentModel()
    model.fit(TRAIN_TEXTS, TRAIN_LABELS)
    preds = model.predict_batch(TEST_TEXTS)
    assert len(preds) == len(TEST_TEXTS)
    assert all(isinstance(p, SentimentPrediction) for p in preds)


def test_unfitted_predict_is_uniform_not_crash() -> None:
    model = TfidfSentimentModel()
    probs = model.predict_proba("anything")
    assert abs(sum(probs.values()) - 1.0) < 1e-6
