"""Event extraction, event deduplication, and timeline construction."""

from __future__ import annotations

from naijafinsent.event_extraction.attributes import (
    ExtractedAttributes,
    actor_roles,
    extract_attributes,
    extract_direction,
    extract_event_date,
    extract_values,
)
from naijafinsent.event_extraction.base import EVENT_LABELS, EventModelMixin, find_evidence_span
from naijafinsent.event_extraction.dedup import (
    DEFAULT_THRESHOLD,
    WEIGHTS,
    EventCluster,
    EventClusterer,
    coverage_intensity,
    score_pair,
    sentiment_shift,
    similarity_features,
    whats_new,
)
from naijafinsent.event_extraction.keywords import TRIGGERS, KeywordEventModel, TriggerSpec
from naijafinsent.event_extraction.timeline import entity_timeline, event_timeline

# ``EventClassifier`` pulls in scikit-learn, which is comparatively expensive to
# import. Resolve it lazily so importing the event package stays cheap.
_LAZY = {"EventClassifier"}


def __getattr__(name: str):
    if name in _LAZY:
        from naijafinsent.event_extraction.tfidf import EventClassifier  # noqa: PLC0415

        return EventClassifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EventClassifier",
    "EVENT_LABELS",
    "EventModelMixin",
    "find_evidence_span",
    "ExtractedAttributes",
    "extract_attributes",
    "extract_direction",
    "extract_event_date",
    "extract_values",
    "actor_roles",
    "KeywordEventModel",
    "TriggerSpec",
    "TRIGGERS",
    "EventCluster",
    "EventClusterer",
    "DEFAULT_THRESHOLD",
    "WEIGHTS",
    "score_pair",
    "similarity_features",
    "whats_new",
    "coverage_intensity",
    "sentiment_shift",
    "event_timeline",
    "entity_timeline",
]
