"""Tests for ``naijafinsent.annotation.validate``.

One valid record passes; every rule violation in the guide is caught.
"""

from __future__ import annotations

from naijafinsent.annotation.validate import (
    RULE_ENTITY_TYPE,
    RULE_EVENT_EVIDENCE,
    RULE_EVENT_TYPE,
    RULE_MONEY_CURRENCY,
    RULE_MONEY_UNIT,
    RULE_SENTIMENT_LABEL,
    RULE_SENTIMENT_TARGET,
    RULE_SPAN_BOUNDS,
    RULE_SPAN_OVERLAP,
    RULE_SPAN_TEXT,
    validate_dataset,
    validate_record,
)
from naijafinsent.schemas import (
    AnnotationRecord,
    EntitySpan,
    EntityType,
    EventAnnotation,
    EventType,
    MoneyAnnotation,
    SentimentAnnotation,
    SentimentLabel,
)

TEXT = "GTCO said profit rose 12% to N120bn as the CBN held the MPR."


def _valid_record() -> AnnotationRecord:
    # Offsets verified against TEXT.
    gtco = EntitySpan(start=0, end=4, text="GTCO", entity_type=EntityType.TICKER)
    money = EntitySpan(start=29, end=35, text="N120bn", entity_type=EntityType.MONEY)
    cbn = EntitySpan(start=43, end=46, text="CBN", entity_type=EntityType.REGULATOR)
    mpr = EntitySpan(start=56, end=59, text="MPR", entity_type=EntityType.EVENT_TRIGGER)
    assert TEXT[gtco.start : gtco.end] == gtco.text
    assert TEXT[money.start : money.end] == money.text
    assert TEXT[cbn.start : cbn.end] == cbn.text
    assert TEXT[mpr.start : mpr.end] == mpr.text
    return AnnotationRecord(
        item_id="item_1",
        article_id="art_1",
        split="train",
        text=TEXT,
        sentiment=SentimentAnnotation(
            label=SentimentLabel.POSITIVE, annotator="a1", model_prelabel=False
        ),
        spans=[gtco, money, cbn, mpr],
        money=[
            MoneyAnnotation(span=money, value=120.0, currency="NGN", unit="billion"),
        ],
        events=[
            EventAnnotation(
                event_type=EventType.EARNINGS,
                evidence_span=EntitySpan(
                    start=10, end=24, text="profit rose 12", entity_type=EntityType.EVENT_TRIGGER
                ),
            )
        ],
    )


def _rules(problems: list[str]) -> set[str]:
    return {p.split("]", 1)[0].lstrip("[") for p in problems}


def test_valid_record_passes() -> None:
    assert validate_record(_valid_record()) == []


def test_span_out_of_bounds() -> None:
    record = _valid_record()
    record.spans.append(
        EntitySpan(start=60, end=200, text="x", entity_type=EntityType.ORG)
    )
    problems = validate_record(record)
    assert RULE_SPAN_BOUNDS in _rules(problems)


def test_span_text_mismatch() -> None:
    record = _valid_record()
    record.spans.append(
        EntitySpan(start=0, end=4, text="XXXX", entity_type=EntityType.ORG)
    )
    problems = validate_record(record)
    assert RULE_SPAN_TEXT in _rules(problems)
    # start=0,end=4 also overlaps the TICKER span -> cross-type overlap reported too.
    assert RULE_SPAN_OVERLAP in _rules(problems)


def test_overlapping_cross_type_spans() -> None:
    record = _valid_record()
    # 0:4 is TICKER; add an ORG span that partially overlaps it.
    record.spans.append(
        EntitySpan(start=2, end=6, text=TEXT[2:6], entity_type=EntityType.ORG)
    )
    problems = validate_record(record)
    assert RULE_SPAN_OVERLAP in _rules(problems)


def test_same_type_same_offsets_not_overlap_but_duplicate_ok() -> None:
    # Two identical TICKER spans: not a cross-type overlap (duplicate reported
    # under its own rule, which is acceptable, but never overlap).
    record = _valid_record()
    record.spans.append(
        EntitySpan(start=0, end=4, text="GTCO", entity_type=EntityType.TICKER)
    )
    problems = validate_record(record)
    assert RULE_SPAN_OVERLAP not in _rules(problems)


def test_bad_entity_type() -> None:
    record = _valid_record()
    # Bypass the enum by using model_construct to simulate a bad import.
    bad = EntitySpan.model_construct(
        start=43, end=46, text="CBN", entity_type="NOT_A_TYPE"
    )
    record.spans.append(bad)
    problems = validate_record(record)
    assert RULE_ENTITY_TYPE in _rules(problems)


def test_bad_event_type() -> None:
    record = _valid_record()
    bad_event = EventAnnotation.model_construct(
        event_type="not_an_event",
        evidence_span=EntitySpan(
            start=43, end=46, text="CBN", entity_type=EntityType.REGULATOR
        ),
        entities=[],
        annotator="a1",
        model_prelabel=False,
    )
    record.events.append(bad_event)
    problems = validate_record(record)
    assert RULE_EVENT_TYPE in _rules(problems)


def test_event_evidence_missing() -> None:
    record = _valid_record()
    record.events.append(
        EventAnnotation(event_type=EventType.DIVIDEND, evidence_span=None)
    )
    problems = validate_record(record)
    assert RULE_EVENT_EVIDENCE in _rules(problems)


def test_bad_sentiment_label() -> None:
    record = _valid_record()
    bad = SentimentAnnotation.model_construct(
        task="sentiment", label="very_positive", target_entity=None,
        rationale_span=None, annotator="a1", model_prelabel=False,
    )
    record.sentiment = bad
    problems = validate_record(record)
    assert RULE_SENTIMENT_LABEL in _rules(problems)


def test_entity_sentiment_requires_target() -> None:
    record = _valid_record()
    record.sentiment = SentimentAnnotation(
        task="entity_sentiment", label=SentimentLabel.NEGATIVE, target_entity=None
    )
    problems = validate_record(record)
    assert RULE_SENTIMENT_TARGET in _rules(problems)


def test_document_sentiment_must_not_have_target() -> None:
    record = _valid_record()
    record.sentiment = SentimentAnnotation(
        task="sentiment", label=SentimentLabel.POSITIVE, target_entity="gtco"
    )
    problems = validate_record(record)
    assert RULE_SENTIMENT_TARGET in _rules(problems)


def test_inferred_money_unit_is_caught() -> None:
    record = _valid_record()
    money_span = EntitySpan(start=29, end=35, text="N120bn", entity_type=EntityType.MONEY)
    # The span says "N2" with no scale word, but the annotation claims "billion".
    bare = EntitySpan(start=29, end=31, text="N1", entity_type=EntityType.MONEY)
    assert TEXT[bare.start : bare.end] == bare.text
    record.money = [MoneyAnnotation(span=bare, value=1.0, currency="NGN", unit="billion")]
    problems = validate_record(record)
    assert RULE_MONEY_UNIT in _rules(problems)
    # sanity: the well-formed one has no money-unit problem
    assert RULE_MONEY_UNIT not in _rules(
        validate_record(
            AnnotationRecord(
                item_id="i", article_id="a", split="train", text=TEXT,
                money=[MoneyAnnotation(span=money_span, value=120.0, currency="NGN",
                                       unit="billion")],
            )
        )
    )


def test_bad_currency() -> None:
    record = _valid_record()
    money = EntitySpan(start=29, end=35, text="N120bn", entity_type=EntityType.MONEY)
    record.money = [MoneyAnnotation(span=money, value=120.0, currency="XYZ", unit="billion")]
    problems = validate_record(record)
    assert RULE_MONEY_CURRENCY in _rules(problems)


def test_validate_dataset_summary() -> None:
    good = _valid_record()
    bad = _valid_record()
    bad.spans.append(EntitySpan(start=60, end=200, text="x", entity_type=EntityType.ORG))
    report = validate_dataset([good, bad])
    assert report["n_records"] == 2
    assert report["n_valid"] == 1
    assert report["n_invalid"] == 1
    assert RULE_SPAN_BOUNDS in report["by_rule"]
