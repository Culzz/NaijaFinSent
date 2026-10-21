"""Tests for ``naijafinsent.annotation.convert``: round-trip and BIO alignment."""

from __future__ import annotations

import json

from naijafinsent.annotation.convert import (
    bio_to_spans,
    doccano_to_records,
    label_studio_to_records,
    spans_to_bio,
    to_event_jsonl,
    to_sentiment_jsonl,
    to_token_jsonl,
    tokenize_with_offsets,
    write_training_jsonl,
)
from naijafinsent.schemas import (
    AnnotationRecord,
    EntitySpan,
    EntityType,
    EventAnnotation,
    EventType,
    SentimentAnnotation,
    SentimentLabel,
)

TEXT = "GTCO profit rose to N120bn; the CBN held the MPR."


def _record() -> AnnotationRecord:
    spans = [
        EntitySpan(start=0, end=4, text="GTCO", entity_type=EntityType.TICKER),
        EntitySpan(start=20, end=26, text="N120bn", entity_type=EntityType.MONEY),
        EntitySpan(start=32, end=35, text="CBN", entity_type=EntityType.REGULATOR),
        EntitySpan(start=45, end=48, text="MPR", entity_type=EntityType.EVENT_TRIGGER),
    ]
    for s in spans:
        assert TEXT[s.start : s.end] == s.text
    return AnnotationRecord(
        item_id="item_1",
        article_id="art_1",
        split="train",
        text=TEXT,
        sentiment=SentimentAnnotation(label=SentimentLabel.POSITIVE),
        spans=spans,
        events=[
            EventAnnotation(
                event_type=EventType.EARNINGS,
                evidence_span=EntitySpan(
                    start=5, end=24, text="profit rose to N120", entity_type=EntityType.EVENT_TRIGGER
                ),
            )
        ],
    )


# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------

def test_tokenize_offsets_reconstruct_text() -> None:
    for text in [
        TEXT,
        "Airtel Africa's revenue grew 20%.",
        "  leading and trailing  ",
        "trailing.",
        "N1,540/$ rate",
    ]:
        tokens = tokenize_with_offsets(text)
        for tok, start, end in tokens:
            assert text[start:end] == tok
        # joining tokens with original gaps reconstructs the text
        rebuilt = ""
        cursor = 0
        for tok, start, end in tokens:
            rebuilt += text[cursor:start] + tok
            cursor = end
        rebuilt += text[cursor:]
        assert rebuilt == text


def test_tokenize_empty() -> None:
    assert tokenize_with_offsets("") == []
    assert tokenize_with_offsets("   ") == []


# --------------------------------------------------------------------------
# BIO alignment
# --------------------------------------------------------------------------

def test_bio_alignment_preserves_offsets() -> None:
    record = _record()
    tokens, tags = spans_to_bio(record.text, record.spans)
    assert len(tokens) == len(tags)
    # Every tag is O or X-TYPE with a valid type.
    valid_types = {t.value for t in EntityType}
    for tag in tags:
        if tag != "O":
            prefix, _, etype = tag.partition("-")
            assert prefix in ("B", "I")
            assert etype in valid_types

    # Round-trip: BIO back to spans must reproduce the original spans.
    recovered = bio_to_spans(tokens, tags, record.text)
    got = sorted((s.start, s.end, s.entity_type.value) for s in recovered)
    want = sorted((s.start, s.end, s.entity_type.value) for s in record.spans)
    assert got == want


def test_bio_iob_valid_and_before_i() -> None:
    record = _record()
    _tokens, tags = spans_to_bio(record.text, record.spans)
    for i, tag in enumerate(tags):
        if tag.startswith("I-"):
            assert i > 0
            assert tags[i - 1] != "O", f"I- tag at {i} not preceded by an entity tag"


def test_bio_multi_token_entity() -> None:
    text = "Dangote Cement and BUA Cement rose."
    dc = EntitySpan(start=0, end=14, text="Dangote Cement", entity_type=EntityType.ORG)
    bual = EntitySpan(start=19, end=25, text="BUA Ce", entity_type=EntityType.ORG)
    # Use the real secondary span to keep offsets honest.
    bual = EntitySpan(start=19, end=29, text="BUA Cement", entity_type=EntityType.ORG)
    assert text[dc.start : dc.end] == dc.text
    assert text[bual.start : bual.end] == bual.text
    tokens, tags = spans_to_bio(text, [dc, bual])
    assert tags[0] == "B-ORG"
    assert tags[1] == "I-ORG"
    assert tags[3] == "B-ORG"
    assert tags[4] == "I-ORG"


def test_bio_partial_token_overlap_deterministic() -> None:
    text = "N120bn"
    tokens, tags = spans_to_bio(text, [
        EntitySpan(start=0, end=6, text="N120bn", entity_type=EntityType.MONEY),
    ])
    # "N120bn" tokenises as one word token (digits/letters run).
    assert tokens == ["N120bn"]
    assert tags == ["B-MONEY"]


def test_bio_no_spans_all_o() -> None:
    tokens, tags = spans_to_bio(TEXT, [])
    assert set(tags) == {"O"}
    assert len(tokens) == len(tags)


# --------------------------------------------------------------------------
# Label Studio import
# --------------------------------------------------------------------------

def test_label_studio_round_trip() -> None:
    payload = [
        {
            "id": 1,
            "data": {"text": TEXT},
            "meta": {"article_id": "art_1", "split": "train"},
            "annotations": [
                {
                    "result": [
                        {"from_name": "sentiment", "value": {"choices": ["positive"]}},
                        {
                            "from_name": "ner",
                            "value": {"start": 0, "end": 4, "labels": ["TICKER"]},
                        },
                        {
                            "from_name": "ner",
                            "value": {"start": 37, "end": 40, "labels": ["REGULATOR"]},
                        },
                    ]
                }
            ],
        }
    ]
    records = label_studio_to_records(payload)
    assert len(records) == 1
    rec = records[0]
    assert rec.sentiment is not None
    assert rec.sentiment.label.value == "positive"
    assert {(s.start, s.end, s.entity_type.value) for s in rec.spans} == {
        (0, 4, "TICKER"),
        (37, 40, "REGULATOR"),
    }
    assert all(TEXT[s.start : s.end] == s.text for s in rec.spans)


# --------------------------------------------------------------------------
# Doccano import
# --------------------------------------------------------------------------

def test_doccano_round_trip() -> None:
    line = json.dumps(
        {
            "id": 7,
            "text": TEXT,
            "labels": [[0, 4, "TICKER"], [24, 30, "MONEY"]],
            "category": "neutral",
            "meta": {"article_id": "art_2", "split": "dev"},
        }
    )
    records = doccano_to_records([line])
    assert len(records) == 1
    rec = records[0]
    assert rec.split == "dev"
    assert rec.article_id == "art_2"
    assert rec.sentiment is not None and rec.sentiment.label.value == "neutral"
    assert all(TEXT[s.start : s.end] == s.text for s in rec.spans)


# --------------------------------------------------------------------------
# Training exports
# --------------------------------------------------------------------------

def test_training_jsonl_exports(tmp_path) -> None:
    records = [_record()]

    n_sent = write_training_jsonl(records, tmp_path / "sent.jsonl", task="sentiment")
    assert n_sent == 1
    row = json.loads((tmp_path / "sent.jsonl").read_text(encoding="utf-8").strip())
    assert row["label"] == "positive"

    n_tok = write_training_jsonl(records, tmp_path / "tok.jsonl", task="token")
    assert n_tok == 1
    tok_row = json.loads((tmp_path / "tok.jsonl").read_text(encoding="utf-8").strip())
    assert len(tok_row["tokens"]) == len(tok_row["tags"])

    n_ev = write_training_jsonl(records, tmp_path / "ev.jsonl", task="events")
    assert n_ev == 1
    ev_row = json.loads((tmp_path / "ev.jsonl").read_text(encoding="utf-8").strip())
    assert ev_row["event_type"] == "earnings"

    # generators produce the expected shapes directly
    assert next(iter(to_sentiment_jsonl(records)))["task"] == "sentiment"
    assert next(iter(to_token_jsonl(records)))["task"] == "ner"
    assert next(iter(to_event_jsonl(records)))["task"] == "events"
