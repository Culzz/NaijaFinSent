"""Quick smoke check for the event-extraction package (not a pytest file)."""
from __future__ import annotations

from datetime import date

from naijafinsent.event_extraction import (
    EventClusterer,
    KeywordEventModel,
    extract_event_date,
    whats_new,
)


TEXT = (
    "The Central Bank of Nigeria raised the monetary policy rate by 200 basis points "
    "to 24.75 percent on 19 February 2026. Access Holdings posted a profit of N459 "
    "billion for the full year. The bank declared a final dividend of N2.00 per share. "
    "The naira closed at N1,510 per dollar in the parallel market yesterday."
)


def main() -> None:
    model = KeywordEventModel()
    events = model.predict(TEXT)
    print(f"events: {len(events)}")
    for ev in events:
        print(" -", ev.event_type.value, ev.confidence, ev.evidence[0].text[:70])

    assert events, "expected at least one event"
    assert all(ev.evidence for ev in events), "every event needs evidence"

    clusterer = EventClusterer()
    rows = clusterer.add_many(events)
    print("clusters:", {r["cluster_id"] for r in rows})

    d, basis = extract_event_date(TEXT, publish_date=date(2026, 2, 20))
    print("event date:", d, basis)
    assert d == date(2026, 2, 19), d

    first = clusterer.clusters[rows[0]["cluster_id"]]
    print("whats_new:", whats_new(first, events[0]))
    print("SMOKE OK")


if __name__ == "__main__":
    main()
