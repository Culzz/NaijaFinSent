"""Tests for event-level deduplication, novelty, and narrative signals.

Event dedup is a different question from article dedup: two articles can be
textually distinct while reporting the *same* real-world event, and the same
article can carry several events.
"""

from __future__ import annotations

from datetime import date

import pytest

from naijafinsent.event_extraction.dedup import (
    EventCluster,
    EventClusterer,
    WEIGHTS,
    coverage_intensity,
    score_pair,
    sentiment_shift,
    similarity_features,
    whats_new,
)
from naijafinsent.schemas import (
    EntityPrediction,
    EntitySpan,
    EventPrediction,
    EventType,
    EvidenceSpan,
    ModelRef,
)

MODEL_REF = ModelRef(name="test-event", version="0.0.1", task="events", calibrated=False)


def make_event(
    text: str,
    *,
    event_type="cbn_policy",
    event_date: date | None = date(2026, 10, 24),
    entities: list[tuple[int, int, str]] | None = None,
    confidence: float = 0.7,
    attributes: dict | None = None,
) -> EventPrediction:
    """Build an EventPrediction for clustering tests."""
    evs: list[EntityPrediction] = []
    for start, end, name in entities or []:
        evs.append(
            EntityPrediction(
                span=EntitySpan(start=start, end=end, text=name, entity_type="ORG"),
                canonical_name=name,
            )
        )
    return EventPrediction(
        event_type=EventType(event_type),
        confidence=confidence,
        event_date=event_date,
        entities=evs,
        evidence=[EvidenceSpan(text=text, start=0, end=min(len(text), 120))],
        attributes=attributes or {},
        model=MODEL_REF,
    )


# ---------------------------------------------------------------------------
# score_pair / similarity features
# ---------------------------------------------------------------------------

def test_weights_sum_to_one_and_are_documented():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert set(WEIGHTS) == {"type", "entities", "date", "text"}


def test_identical_events_score_one():
    a = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")])
    b = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")])
    score, feats = score_pair(a, b)
    assert score == 1.0
    assert all(v == 1.0 for v in feats.values())


def test_features_decompose_sensibly():
    a = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")])
    b = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")], event_type="fx_move")
    feats = similarity_features(b, a)
    assert feats["type"] == 0.0  # different event type
    assert feats["date"] == 1.0  # same event date
    assert feats["text"] == 1.0  # identical evidence text
    # Text similarity alone cannot offset a type mismatch under the weights.
    score, _ = score_pair(b, a)
    assert score < 0.75


def test_both_dates_unknown_is_neutral_not_positive():
    a = make_event("The CBN raised the rate.", event_date=None)
    b = make_event("The CBN raised the rate.", event_date=None)
    feats = similarity_features(a, b)
    assert feats["date"] == 0.5  # unknown is neutral, 0.25 only if one side knows


def test_dates_far_apart_contribute_zero():
    a = make_event("The CBN raised the rate.", event_date=date(2026, 1, 1))
    b = make_event("The CBN raised the rate.", event_date=date(2026, 6, 1))
    assert similarity_features(a, b)["date"] == 0.0


# ---------------------------------------------------------------------------
# EventClusterer
# ---------------------------------------------------------------------------

def test_identical_events_merge_into_one_cluster():
    clusterer = EventClusterer()
    a = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")])
    b = make_event("The CBN raised the rate.", entities=[(0, 3, "CBN")])
    c1, score1, _ = clusterer.assign_or_create(a)
    c2, score2, feats2 = clusterer.assign_or_create(b)
    assert c1 is c2
    assert score2 >= clusterer.threshold
    assert len(clusterer.clusters) == 1
    assert len(c2.members) == 2


def test_different_realworld_events_do_not_merge():
    clusterer = EventClusterer()
    a = make_event(
        "The CBN raised the rate sharply today.",
        event_type="cbn_policy",
        entities=[(0, 3, "CBN")],
    )
    b = make_event(
        "Dangote acquired the rival producer in a deal completed today.",
        event_type="mna",
        entities=[(0, 7, "Dangote")],
    )
    c1, _, _ = clusterer.assign_or_create(a)
    c2, score2, feats2 = clusterer.assign_or_create(b)
    # No merge: b gets its own cluster. A brand-new cluster returns the
    # documented sentinel score 1.0 with a {"new": 1.0} feature dict.
    assert c1 is not c2
    assert feats2 == {"new": 1.0}
    assert len(clusterer.clusters) == 2
    # The actual pairwise score confirms the two events stay apart.
    pair_score, _ = score_pair(b, c1.canonical)
    assert pair_score < clusterer.threshold


def test_cluster_ids_are_stable_and_incrementing():
    clusterer = EventClusterer()
    a = make_event("The CBN raised the rate.")
    b = make_event("Dangote acquired a rival producer.")
    c1, _, _ = clusterer.assign_or_create(a)
    c2, _, _ = clusterer.assign_or_create(b)
    assert c1.cluster_id != c2.cluster_id
    assert c1.cluster_id.startswith("evt-")


def test_add_many_returns_one_row_per_event():
    clusterer = EventClusterer()
    rows = clusterer.add_many(
        [
            make_event("The CBN raised the rate."),
            make_event("The CBN raised the rate."),
        ]
    )
    assert len(rows) == 2
    assert rows[0]["cluster_id"] == rows[1]["cluster_id"]
    assert rows[0]["is_new_cluster"] is True
    assert rows[1]["is_new_cluster"] is False
    assert rows[1]["score"] >= clusterer.threshold


# ---------------------------------------------------------------------------
# Timeline / coverage signals
# ---------------------------------------------------------------------------

def test_cluster_timeline_orders_by_event_date_and_labels_repeats():
    first = make_event("Original report of the rate decision.", event_date=date(2026, 10, 20))
    later = make_event("Original report of the rate decision.", event_date=date(2026, 10, 22))
    clusterer = EventClusterer()
    cluster, _, _ = clusterer.assign_or_create(first)
    cluster, _, _ = clusterer.assign_or_create(later)
    timeline = cluster.timeline()
    assert [t["index"] for t in timeline] == [0, 1]
    assert timeline[0]["relation"] == "originates"
    assert timeline[1]["relation"] == "repeats"
    assert timeline[0]["event_date"] == "2026-10-20"
    assert timeline[1]["event_date"] == "2026-10-22"


def test_whats_new_flags_repeat_and_new_values():
    clusterer = EventClusterer()
    first = make_event(
        "The CBN raised the rate by 25 basis points.",
        entities=[(0, 3, "CBN")],
        attributes={"values": [{"text": "25 basis points"}]},
    )
    cluster, _, _ = clusterer.assign_or_create(first)

    repeat = make_event(
        "The CBN raised the rate by 25 basis points.",
        entities=[(0, 3, "CBN")],
        attributes={"values": [{"text": "25 basis points"}]},
    )
    first_report = whats_new(cluster, repeat)
    # Nothing new vs the canonical event itself.
    assert first_report["is_repeat"] is True

    updated = make_event(
        "The CBN raised the rate by 50 basis points.",
        entities=[(0, 3, "CBN")],
        attributes={"values": [{"text": "50 basis points"}]},
    )
    second = whats_new(cluster, updated)
    assert second["is_repeat"] is False
    assert second["new_values"] == ["50 basis points"]
    assert 0.0 <= second["novelty_score"] <= 1.0
    assert second["novelty_score"] > 0


def test_whats_new_mines_money_values_from_the_evidence_text():
    """Events whose pipeline did not attach parsed values still contribute
    novel numeric facts: the verbatim money mentions are mined from evidence."""
    clusterer = EventClusterer()
    first = make_event(
        "Zenith Bank raised ₦150 billion in fresh capital.",
        event_type="capital_raise",
    )
    cluster, _, _ = clusterer.assign_or_create(first)
    updated = make_event(
        "Zenith Bank upsized the raise to ₦300 billion.",
        event_type="capital_raise",
    )
    report = whats_new(cluster, updated)
    assert report["new_values"] == ["₦300 billion"]
    assert report["is_repeat"] is False


def test_coverage_intensity_counts_records_per_period():
    cluster = EventCluster(
        cluster_id="evt-1",
        event_type="cbn_policy",
        canonical=make_event("a"),
        members=[
            make_event("a", event_date=date(2026, 10, 20)),
            make_event("b", event_date=date(2026, 10, 20)),
            make_event("c", event_date=None),
        ],
    )
    series = coverage_intensity(cluster.timeline())
    by_period = {row["period"]: row["count"] for row in series}
    assert by_period["2026-10-20"] == 2
    assert by_period["unknown"] == 1


def test_sentiment_shift_windows_and_caveat():
    series = [
        {"period": "2026-01", "score": -1},
        {"period": "2026-02", "score": -1},
        {"period": "2026-03", "score": -1},
        {"period": "2026-04", "score": 1},
        {"period": "2026-05", "score": 1},
        {"period": "2026-06", "score": 1},
    ]
    out = sentiment_shift(series, window=3)
    assert out["shift"] == 2.0  # +1 recent vs -1 prior
    assert out["interpretation"] == "more positive language"
    # The product is an association in language, never a causal claim.
    assert "not causation" in out["caveat"]


def test_sentiment_shift_insufficient_data_is_explicit():
    out = sentiment_shift([{"period": "2026-01", "score": 1}])
    assert out["shift"] is None
    assert out["interpretation"] == "insufficient data"


def test_sentiment_shift_stable_band():
    series = [{"period": f"2026-0{i}", "score": 1} for i in range(1, 7)]
    out = sentiment_shift(series, window=3)
    assert out["shift"] == 0.0
    assert out["interpretation"] == "stable"
