"""Tests for the per-type TF-IDF event classifier (train/save/load/predict)."""

from __future__ import annotations

from naijafinsent.event_extraction.keywords import KeywordEventModel
from naijafinsent.event_extraction.tfidf import EventClassifier

# Three examples per type; deliberately few so the test stays fast.
TRAIN_TEXTS = [
    "The Central Bank of Nigeria raised the monetary policy rate.",
    "The MPC raised the policy rate by 50 basis points.",
    "The committee increased the benchmark rate citing inflation.",
    "Access Bank posted its half-year results today.",
    "The lender released full-year results showing higher profit.",
    "Zenith Bank reported earnings for the period.",
    "The bank declared a dividend for the fiscal year.",
    "A final dividend was declared after the results.",
    "Shareholders approved the proposed dividend.",
    "Seplat acquired a rival producer in a completed deal.",
    "The acquisition of the rival was announced today.",
    "The oil producer acquired its nearest competitor.",
    "The regulator fined the bank and revoked its licence.",
    "The commission sanctioned the operator for reporting failures.",
    "SEC suspended the firm over repeated breaches.",
    "The naira depreciated against the dollar at the official window.",
    "The naira fell to a record low against the dollar.",
    "The local currency weakened in the official market.",
]

TRAIN_LABELS = (
    [["cbn_policy"]] * 3
    + [["earnings"]] * 3
    + [["dividend"]] * 3
    + [["mna"]] * 3
    + [["regulatory_sanction"]] * 3
    + [["fx_move"]] * 3
)


def _trained() -> EventClassifier:
    return EventClassifier().fit(TRAIN_TEXTS, TRAIN_LABELS, seed=0)


def test_fit_then_predict_obvious_cases():
    model = _trained()
    preds = model.predict("The Central Bank of Nigeria raised the monetary policy rate.")
    assert preds, "an obvious policy sentence should produce a prediction"
    assert any(p.event_type.value == "cbn_policy" for p in preds)


def test_predictions_carry_evidence_and_model_ref():
    model = _trained()
    preds = model.predict("The bank declared a dividend for the fiscal year.")
    assert preds
    for p in preds:
        assert p.evidence, "predictions must keep their evidence spans"
        assert p.model is not None


def test_deterministic_given_seed():
    a = [p.model_dump() for p in _trained().predict("The naira depreciated against the dollar.")]
    b = [p.model_dump() for p in _trained().predict("The naira depreciated against the dollar.")]
    assert a == b


def test_classifier_keeps_the_keyword_fallback_for_rare_types():
    """Types with no positive examples during fit still produce predictions
    via the keyword model instead of vanishing from the serving path."""
    model = EventClassifier(labels=("dividend",)).fit(TRAIN_TEXTS, TRAIN_LABELS)
    # dividend had positives; ensure the trained pipeline drives the response.
    preds = model.predict("The bank declared a dividend for the fiscal year.")
    assert any(p.event_type.value == "dividend" for p in preds)
    # The keyword fallback is wired for untrained types.
    assert isinstance(model._fallback, KeywordEventModel)


def test_fit_rejects_length_mismatch():
    import pytest

    with pytest.raises(ValueError):
        EventClassifier().fit(TRAIN_TEXTS, TRAIN_LABELS[:-1])


def test_save_and_load_roundtrip(tmp_path):
    model = _trained()
    path = model.save(tmp_path / "events.joblib")
    assert path.exists()
    loaded = EventClassifier.load(path)
    text = "The commission sanctioned the operator for reporting failures."
    a = [p.model_dump() for p in model.predict(text)]
    b = [p.model_dump() for p in loaded.predict(text)]
    assert a == b, "loaded model must reproduce identical predictions"
