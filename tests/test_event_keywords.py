"""Tests for the keyword event model.

Contract under test: deterministic, evidence-backed, honest — the model date
field stays None (the attribute extractor owns dates) and every prediction
carries an exact evidence span inside the original text.
"""

from __future__ import annotations

from naijafinsent.event_extraction.keywords import KeywordEventModel
from naijafinsent.schemas import EntityPrediction, EntitySpan, EventType

MODEL = KeywordEventModel()


def _types(text: str, **kwargs) -> list[EventType]:
    return [e.event_type for e in MODEL.predict(text, **kwargs)]


def test_detects_cbn_policy_with_evidence_span():
    text = (
        "The Central Bank of Nigeria raised the monetary policy rate by "
        "50 basis points to 27.5 percent, citing inflation."
    )
    preds = MODEL.predict(text)
    assert EventType.CBN_POLICY in [p.event_type for p in preds]
    p = next(p for p in preds if p.event_type == EventType.CBN_POLICY)
    assert 0.5 <= p.confidence <= 0.9  # rules are never certain
    assert p.evidence, "every event prediction must carry evidence"
    span = p.evidence[0]
    assert text[span.start : span.end] == span.text  # offsets slice the original
    assert "monetary policy" in span.text or "rate" in span.text
    # Dates belong to the attribute extractor, not the trigger model.
    assert p.event_date is None


def test_detects_earnings_and_dividend_separately():
    text = (
        "Access Bank posted full-year results and declared a final dividend "
        "for 2025."
    )
    types = _types(text)
    assert EventType.EARNINGS in types
    assert EventType.DIVIDEND in types


def test_detects_mna_sanction_capital_raise_fx_move():
    assert EventType.MNA in _types(
        "Seplat acquired a rival producer in a deal announced today."
    )
    assert EventType.REGULATORY_SANCTION in _types(
        "The regulator fined the bank and revoked its operating licence."
    )
    assert EventType.CAPITAL_RAISE in _types(
        "Zenith Bank raised fresh capital through a rights issue."
    )
    assert EventType.FX_MOVE in _types(
        "The naira depreciated against the dollar at the official window."
    )


def test_no_prediction_for_plain_text():
    preds = MODEL.predict("Shares traded quietly in Lagos with no news flow.")
    assert preds == []


def test_empty_and_whitespace_text_short_circuit():
    assert MODEL.predict("") == []
    assert MODEL.predict("   \n\t  ") == []


def test_deterministic_across_repeated_calls():
    text = "The CBN raised the monetary policy rate."
    a = [p.model_dump() for p in MODEL.predict(text)]
    b = [p.model_dump() for p in MODEL.predict(text)]
    assert a == b


def test_model_ref_is_attached_and_honest():
    text = "The bank posted its half-year results."
    (pred,) = MODEL.predict(text)
    ref = pred.model
    assert ref is not None
    assert ref.name == MODEL.name


def test_min_confidence_filters_weak_hits():
    text = "The CBN raised the monetary policy rate."
    default = MODEL.predict(text)
    assert default  # passes at the default threshold
    strict = KeywordEventModel(min_confidence=0.95).predict(text)
    assert strict == []


def test_entities_inside_the_sentence_become_actors():
    text = "Zenith Bank posted strong results for the year."
    entity = EntityPrediction(
        span=EntitySpan(start=0, end=11, text="Zenith Bank", entity_type="ORG"),
        canonical_name="Zenith Bank",
    )
    (pred,) = MODEL.predict(text, entities=[entity])
    assert pred.entities
    assert pred.entities[0].canonical_name == "Zenith Bank"


def test_entities_outside_the_event_sentence_are_excluded():
    text = "Zenith Bank reported strong earnings. The weather in Lagos was mild."
    entity = EntityPrediction(
        span=EntitySpan(start=0, end=11, text="Zenith Bank", entity_type="ORG"),
        canonical_name="Zenith Bank",
    )
    pantry = EntityPrediction(
        span=EntitySpan(start=52, end=57, text="Lagos", entity_type="ORG"),
        canonical_name="Lagos",
    )
    preds = MODEL.predict(text, entities=[entity, pantry])
    preds = [p for p in preds if p.event_type == EventType.EARNINGS]
    assert preds
    actors = {e.canonical_name for e in preds[0].entities}
    assert "Zenith Bank" in actors


def test_one_event_type_per_sentence_not_duplicated():
    text = "The CBN raised the monetary policy rate. The naira firmed."
    preds = MODEL.predict(text)
    cbn = [p for p in preds if p.event_type == EventType.CBN_POLICY]
    assert len(cbn) == 1


def test_attributes_describe_the_trigger():
    text = "The CBN raised the monetary policy rate."
    (pred,) = MODEL.predict(text)
    assert pred.attributes["trigger"] == "keyword"
    assert "sentence_index" in pred.attributes
