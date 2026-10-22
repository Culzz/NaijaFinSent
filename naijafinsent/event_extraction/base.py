"""Event-extraction model interface.

An event model maps article text to zero or more :class:`EventPrediction`s.
Every prediction MUST carry an evidence span: a bare label with no span is not
an acceptable output, because the app promises to link each event to its
supporting text.

``event_date`` is the date the event happened; it is never the publish date.
The pipeline stores those separately (see ``attributes.extract_event_date``).
"""

from __future__ import annotations

from typing import Protocol

from naijafinsent.constants import EVENT_TYPES
from naijafinsent.schemas import EntityPrediction, EventPrediction

EVENT_LABELS: tuple[str, ...] = EVENT_TYPES


class BaseEventModel(Protocol):
    """Structural interface every event model satisfies."""

    name: str
    version: str
    task: str
    calibrated: bool

    def predict(
        self, text: str, entities: list[EntityPrediction] | None = None
    ) -> list[EventPrediction]: ...


class EventModelMixin:
    """Shared helpers for concrete event models.

    Kept as a mixin rather than a base class so models can inherit from
    sklearn/transformers classes freely.
    """

    name: str = "event-model"
    version: str = "0.0.0"
    task: str = "events"
    calibrated: bool = False

    def predict(
        self, text: str, entities: list[EntityPrediction] | None = None
    ) -> list[EventPrediction]:  # pragma: no cover - overridden
        raise NotImplementedError


def find_evidence_span(
    text: str, patterns: list[str], *, window: int = 0
) -> tuple[int, int] | None:
    """Return the first sentence containing any pattern, as a char span.

    Used by rule-based models so their evidence is a real, quotable span of the
    source text rather than a synthetic snippet.
    """
    import re

    lowered = text.lower()
    for pat in patterns:
        m = re.search(pat, lowered)
        if not m:
            continue
        start = m.start()
        # Expand to sentence boundaries so the evidence is human-readable.
        left = max(
            text.rfind(". ", 0, start),
            text.rfind("! ", 0, start),
            text.rfind("? ", 0, start),
            text.rfind("\n", 0, start),
        )
        begin = 0 if left == -1 else left + 2
        right_candidates = [
            text.find(". ", m.end()),
            text.find("! ", m.end()),
            text.find("? ", m.end()),
            text.find("\n", m.end()),
        ]
        ends = [c + 1 for c in right_candidates if c != -1]
        end = min(ends) if ends else len(text)
        if window:
            begin = max(0, begin - window)
            end = min(len(text), end + window)
        while begin < end and text[begin] == " ":
            begin += 1
        return (begin, end)
    return None
