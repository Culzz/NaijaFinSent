"""Timeline construction for events and entities.

All timelines are coverage timelines: they describe when a story was reported
and what the article language was. They are not price series and carry no
predictive claim.
"""

from __future__ import annotations

from datetime import date

from naijafinsent.event_extraction.dedup import (
    EventCluster,
    coverage_intensity,
    sentiment_shift,
)


def event_timeline(cluster: EventCluster) -> dict:
    """One cluster's ordered coverage, with new-vs-repeated marking."""
    items = sorted(
        cluster.members,
        key=lambda e: (
            e.event_date or date.min,
            e.evidence[0].start if e.evidence else 0,
        ),
    )
    rows = []
    seen_signatures: set[str] = set()
    for i, ev in enumerate(items):
        signature = " ".join(sorted(
            {x.text.lower() for x in ev.evidence}
        ))
        repeated = signature in seen_signatures
        seen_signatures.add(signature)
        rows.append(
            {
                "index": i,
                "event_date": ev.event_date.isoformat() if ev.event_date else None,
                "event_type": ev.event_type.value,
                "confidence": ev.confidence,
                "relation": "originates" if i == 0 else ("repeats" if repeated else "updates"),
                "evidence": [x.model_dump() for x in ev.evidence],
            }
        )
    return {
        "cluster_id": cluster.cluster_id,
        "event_type": cluster.event_type,
        "first_seen": cluster.first_seen.isoformat() if cluster.first_seen else None,
        "last_seen": cluster.last_seen.isoformat() if cluster.last_seen else None,
        "items": rows,
        "coverage_intensity": coverage_intensity(rows),
        "caveat": "Coverage measurement. Not investment advice, not a price series.",
    }


def entity_timeline(
    entity_name: str,
    events: list[dict],
    *,
    sentiment_series: list[dict] | None = None,
) -> dict:
    """Aggregate an entity's related events plus its coverage-sentiment trend.

    ``events`` are pre-serialised event rows (see ``event_timeline``); this
    function deliberately takes plain dicts so the API can build it straight
    from a database query without re-running the model.
    """
    related = [
        e for e in events
        if entity_name.lower() in str(e.get("entities", "")).lower()
        or any(
            entity_name.lower() in str(ev.get("text", "")).lower()
            for ev in e.get("evidence", [])
        )
    ]
    related.sort(key=lambda e: (e.get("event_date") or "", e.get("index", 0)))
    return {
        "entity": entity_name,
        "events": related,
        "event_count": len(related),
        "coverage_sentiment": sentiment_series or [],
        "sentiment_shift": sentiment_shift(sentiment_series or []),
        "caveat": (
            "Timeline of published coverage language. "
            "Temporal association, not causation; not investment advice."
        ),
    }


__all__ = ["entity_timeline", "event_timeline"]
