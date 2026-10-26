"""Event-level deduplication, novelty scoring, and narrative shift detection.

This is *not* article deduplication (that lives in ``naijafinsent.data.dedup``).
Here we answer a different question: given a newly extracted event, is it the
same underlying real-world event that other articles already reported?

The scoring is deliberately transparent: entities, date proximity, event type,
and text similarity are combined with documented weights so a reviewer can see
*why* two events merged. Anything below the threshold becomes its own cluster
rather than being silently merged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from naijafinsent.event_extraction.attributes import extract_values
from naijafinsent.schemas import EventPrediction

# Weights sum to 1.0. Documented so the merge decision is auditable.
WEIGHTS = {
    "type": 0.30,
    "entities": 0.30,
    "date": 0.20,
    "text": 0.20,
}

DEFAULT_THRESHOLD = 0.62
_DATE_WINDOW_DAYS = 3


def _text_of(event: EventPrediction) -> str:
    return " ".join(e.text for e in event.evidence).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _value_keys(event: EventPrediction) -> set[str]:
    """Verbatim money/percent mentions: parsed attributes plus raw evidence text.

    The evidence text is mined too so events whose pipeline did not attach
    parsed values still contribute novel numeric facts ("50 basis points").
    """
    keys = {str(v.get("text")) for v in (event.attributes or {}).get("values", [])}
    for v in extract_values(_text_of(event)):
        keys.add(v["text"])
    return keys


def _entity_keys(event: EventPrediction) -> set[str]:
    keys: set[str] = set()
    for e in event.entities:
        key = (e.entity_id or e.canonical_name or e.span.text or "").lower().strip()
        if key:
            keys.add(key)
    # Also mine capitalised tokens out of the evidence text so events without a
    # resolved entity still match on the obvious actors.
    for m in re.finditer(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", _text_of(event)):
        tok = m.group(0).lower()
        if tok not in {"the", "a", "an", "this", "that"}:
            keys.add(tok)
    return keys


def similarity_features(
    new: EventPrediction, existing: EventPrediction
) -> dict[str, float]:
    """Return each similarity component in [0, 1] with its name."""
    type_score = 1.0 if new.event_type == existing.event_type else 0.0

    ent_score = _jaccard(_entity_keys(new), _entity_keys(existing))

    date_score = 0.0
    if new.event_date and existing.event_date:
        delta = abs((new.event_date - existing.event_date).days)
        if delta <= _DATE_WINDOW_DAYS:
            date_score = 1.0 - (delta / (_DATE_WINDOW_DAYS + 1))
        else:
            date_score = 0.0
    elif not new.event_date and not existing.event_date:
        # Both unknown: neutral, not evidence of sameness.
        date_score = 0.5
    else:
        date_score = 0.25

    text_score = _jaccard(_tokens(_text_of(new)), _tokens(_text_of(existing)))

    return {
        "type": type_score,
        "entities": ent_score,
        "date": date_score,
        "text": text_score,
    }


def score_pair(new: EventPrediction, existing: EventPrediction) -> tuple[float, dict]:
    """Weighted similarity in [0, 1] plus the feature breakdown."""
    feats = similarity_features(new, existing)
    score = sum(WEIGHTS[k] * v for k, v in feats.items())
    return round(score, 4), feats


@dataclass
class EventCluster:
    """A deduplicated real-world event."""

    cluster_id: str
    event_type: str
    canonical: EventPrediction
    members: list[EventPrediction] = field(default_factory=list)
    first_seen: date | None = None
    last_seen: date | None = None
    novelty_history: list[float] = field(default_factory=list)

    def timeline(self) -> list[dict]:
        ordered = sorted(
            self.members or [self.canonical],
            key=lambda e: (e.event_date or date.min, e.evidence[0].start if e.evidence else 0),
        )
        out = []
        for i, ev in enumerate(ordered):
            out.append(
                {
                    "index": i,
                    "event_date": ev.event_date.isoformat() if ev.event_date else None,
                    "event_type": ev.event_type.value,
                    "confidence": ev.confidence,
                    "evidence": [x.model_dump() for x in ev.evidence],
                    "relation": "originates" if i == 0 else "repeats",
                }
            )
        return out


class EventClusterer:
    """Assigns events to clusters using transparent similarity scoring."""

    def __init__(self, *, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold
        self.clusters: dict[str, EventCluster] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"evt-{self._counter:05d}"

    def assign_or_create(
        self, event: EventPrediction
    ) -> tuple[EventCluster, float, dict]:
        """Return ``(cluster, score, features)`` for the best match or a new one."""
        best: tuple[EventCluster | None, float, dict] = (None, 0.0, {})
        for cluster in self.clusters.values():
            score, feats = score_pair(event, cluster.canonical)
            if score > best[1]:
                best = (cluster, score, feats)

        if best[0] is not None and best[1] >= self.threshold:
            cluster = best[0]
            cluster.members.append(event)
            if event.event_date:
                cluster.last_seen = max(
                    [d for d in (cluster.last_seen, event.event_date) if d]
                )
            return cluster, best[1], best[2]

        cluster = EventCluster(
            cluster_id=self._next_id(),
            event_type=event.event_type.value,
            canonical=event,
            members=[event],
            first_seen=event.event_date,
            last_seen=event.event_date,
        )
        self.clusters[cluster.cluster_id] = cluster
        return cluster, 1.0, {"new": 1.0}

    def add_many(self, events: list[EventPrediction]) -> list[dict]:
        """Cluster a batch and return one summary row per event."""
        rows = []
        for ev in events:
            cluster, score, feats = self.assign_or_create(ev)
            rows.append(
                {
                    "event_type": ev.event_type.value,
                    "cluster_id": cluster.cluster_id,
                    "score": score,
                    "features": feats,
                    "is_new_cluster": len(cluster.members) == 1,
                }
            )
        return rows


# --------------------------------------------------------------------------
# Novelty / narrative signals
# --------------------------------------------------------------------------

def whats_new(cluster: EventCluster, new_event: EventPrediction) -> dict:
    """Describe what this article adds beyond prior coverage of the cluster.

    Returns newly introduced entities, values, dates, and a novelty score in
    [0, 1] where 0 means "pure repeat" and 1 means "everything is new".
    """
    # Identity, not equality: an equal-valued copy of the latest member is
    # exactly the "pure repeat" case and would otherwise make ``prior`` empty
    # (pydantic models compare by value).
    is_latest = any(new_event is m for m in cluster.members)
    prior = cluster.members[:-1] if is_latest else cluster.members
    prior_entities: set[str] = set()
    prior_values: set[str] = set()
    prior_dates: set[str] = set()
    for ev in prior:
        prior_entities |= _entity_keys(ev)
        prior_values |= _value_keys(ev)
        if ev.event_date:
            prior_dates.add(ev.event_date.isoformat())

    new_entities = sorted(_entity_keys(new_event) - prior_entities)
    new_values = sorted(_value_keys(new_event) - prior_values)
    new_dates = sorted(
        ({new_event.event_date.isoformat()} if new_event.event_date else set())
        - prior_dates
    )

    total_signals = len(new_entities) + len(new_values) + len(new_dates)
    if not prior:
        novelty = 1.0
    else:
        denom = max(1, total_signals + len(prior_entities))
        novelty = round(min(1.0, total_signals / denom * 2), 3)

    return {
        "new_entities": new_entities,
        "new_values": new_values,
        "new_dates": new_dates,
        "novelty_score": novelty,
        "is_repeat": total_signals == 0,
    }


def coverage_intensity(timeline: list[dict]) -> list[dict]:
    """Count mentions per day from a timeline (coverage measurement, not sentiment)."""
    counts: dict[str, int] = {}
    for item in timeline:
        key = item.get("event_date") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [{"period": k, "count": v} for k, v in sorted(counts.items())]


def sentiment_shift(series: list[dict], *, window: int = 3) -> dict:
    """Compare mean sentiment over two rolling windows.

    ``series`` items need ``period`` and ``score`` (positive=+1, negative=-1,
    neutral/uncertain=0). The result is explicitly framed as an association in
    reported language, **not** a causal claim about the market.
    """
    scored = [s for s in series if s.get("score") is not None]
    if len(scored) < 2:
        return {
            "shift": None,
            "interpretation": "insufficient data",
            "caveat": "Temporal association in coverage language, not causation.",
        }
    tail = scored[-window:]
    head = scored[max(0, len(scored) - 2 * window) : len(scored) - window] or scored[:1]
    tail_mean = sum(s["score"] for s in tail) / len(tail)
    head_mean = sum(s["score"] for s in head) / len(head)
    shift = round(tail_mean - head_mean, 4)
    if abs(shift) < 0.1:
        label = "stable"
    elif shift > 0:
        label = "more positive language"
    else:
        label = "more negative language"
    return {
        "shift": shift,
        "recent_mean": round(tail_mean, 4),
        "prior_mean": round(head_mean, 4),
        "interpretation": label,
        "caveat": "Temporal association in coverage language, not causation.",
    }


__all__ = [
    "DEFAULT_THRESHOLD",
    "WEIGHTS",
    "EventCluster",
    "EventClusterer",
    "coverage_intensity",
    "score_pair",
    "sentiment_shift",
    "similarity_features",
    "whats_new",
]
