"""Watchlist evaluation: transparent filters, explicit thresholds, deduped alerts.

Design commitments
------------------
* **Transparent thresholds.** Every alert records the threshold that fired and
  the score that cleared it. Nothing is "anomalous" without a stated rule, so a
  user can always answer "why did I get this?".
* **Dedup is structural.** ``alerts.dedup_key`` is derived from the watchlist,
  the matched object and the *reason*, and is UNIQUE in the database. Re-running
  evaluation is therefore idempotent, and a genuine escalation produces a new key
  rather than being swallowed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from naijafinsent.config import Settings, get_settings
from naijafinsent.utils import utcnow
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db import models as m

logger = logging.getLogger(__name__)

#: Default thresholds. Exposed so the API can echo them back in the response.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "min_novelty": 0.0,
    "min_confidence": 0.0,
    "similarity_update": 0.75,
}


@dataclass
class EvaluationOutcome:
    """Result of one watchlist evaluation."""

    watchlist_id: int
    evaluated_at: Any
    candidates: int = 0
    created: list[dict[str, Any]] = field(default_factory=list)
    suppressed: int = 0
    thresholds: dict[str, Any] = field(default_factory=dict)

    @property
    def created_count(self) -> int:
        return len(self.created)

    def as_dict(self) -> dict[str, Any]:
        return {
            "watchlist_id": self.watchlist_id,
            "evaluated_at": _iso(self.evaluated_at),
            "candidates": self.candidates,
            "created": self.created_count,
            "suppressed": self.suppressed,
            "alerts": self.created,
            "thresholds": self.thresholds,
        }


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _matches_keywords(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords if k)


def evaluate_watchlist(
    session: Session,
    watchlist: dict[str, Any],
    *,
    settings: Settings | None = None,
    now: Any | None = None,
) -> EvaluationOutcome:
    """Evaluate one watchlist and persist new alerts.

    Filters applied, in this order (each is a plain, inspectable rule):

    1. ``lookback_days`` window on the event's processing/publish date.
    2. ``event_types`` membership.
    3. ``min_novelty`` on ``financial_events.novelty_score``.
    4. ``min_confidence`` on ``financial_events.confidence``.
    5. ``entity_ids`` via the articles linked to the event.
    6. ``publishers`` via the articles linked to the event.
    7. ``keywords`` against the event title/summary.

    Only ``is_primary`` events are considered, so a cluster of five articles
    about one dividend does not produce five alerts.
    """
    settings = settings or get_settings()
    now = now or utcnow()
    filters = dict(watchlist.get("filters") or {})
    watchlist_id = int(watchlist["id"])

    thresholds = {
        "min_novelty": float(filters.get("min_novelty", DEFAULT_THRESHOLDS["min_novelty"])),
        "min_confidence": float(
            filters.get("min_confidence", DEFAULT_THRESHOLDS["min_confidence"])
        ),
    }
    outcome = EvaluationOutcome(
        watchlist_id=watchlist_id,
        evaluated_at=now,
        thresholds={
            **thresholds,
            "event_types": filters.get("event_types") or [],
            "publishers": filters.get("publishers") or [],
            "entity_ids": filters.get("entity_ids") or [],
            "keywords": filters.get("keywords") or [],
            "lookback_days": int(filters.get("lookback_days", 7)),
        },
    )

    lookback = int(filters.get("lookback_days", 7))
    since: date = (now.date() if hasattr(now, "date") else now) - timedelta(days=lookback)

    stmt = select(m.FinancialEvent).where(
        m.FinancialEvent.is_primary.is_(True),
        m.FinancialEvent.processing_date >= since,
    )
    event_types = filters.get("event_types") or []
    if event_types:
        stmt = stmt.where(m.FinancialEvent.event_type.in_(list(event_types)))

    candidates = list(session.scalars(stmt).all())

    existing_keys = set(
        session.scalars(select(m.Alert.dedup_key).where(m.Alert.watchlist_id == watchlist_id)).all()
    )

    publishers = set(filters.get("publishers") or [])
    entity_ids = set(filters.get("entity_ids") or [])
    keywords = list(filters.get("keywords") or [])

    link_rows = _links_for_events(session, [e.id for e in candidates])

    allowed = 0
    for event in candidates:
        if (event.novelty_score or 0.0) < thresholds["min_novelty"]:
            continue
        if (event.confidence or 0.0) < thresholds["min_confidence"]:
            continue
        if keywords and not _matches_keywords(f"{event.title} {event.summary or ''}", keywords):
            continue

        linked = link_rows.get(event.id, {})
        if publishers and not (publishers & linked.get("publishers", set())):
            continue
        if entity_ids and not (entity_ids & linked.get("entity_ids", set())):
            continue

        allowed += 1
        reason = _reason(event, thresholds, linked)
        # Dedup key: watchlist + event + the reason string. A changed reason
        # (e.g. a higher novelty score) legitimately produces a new alert.
        dedup_key = f"wl{watchlist_id}:ev{event.id}:{_hash_reason(reason)}"

        if dedup_key in existing_keys:
            outcome.suppressed += 1
            continue

        session.add(
            m.Alert(
                watchlist_id=watchlist_id,
                event_id=event.id,
                threshold=thresholds["min_novelty"],
                score=event.novelty_score,
                reason=reason,
                dedup_key=dedup_key,
            )
        )
        outcome.created.append(
            {
                "watchlist_id": watchlist_id,
                "event_id": event.id,
                "threshold": thresholds["min_novelty"],
                "score": event.novelty_score,
                "reason": reason,
                "dedup_key": dedup_key,
                "created_at": _iso(now),
                "delivered_at": None,
                "id": None,
            }
        )
        existing_keys.add(dedup_key)

    outcome.candidates = allowed
    _touch(session, watchlist_id, now)
    logger.info(
        "watchlist %s: candidates=%d created=%d suppressed=%d",
        watchlist_id,
        outcome.candidates,
        len(outcome.created),
        outcome.suppressed,
    )
    return outcome


def _links_for_events(session: Session, event_ids: Sequence[int]) -> dict[int, dict[str, set[Any]]]:
    """One query returning publishers and entity ids per event."""
    if not event_ids:
        return {}
    stmt = (
        select(
            m.EventArticle.event_id,
            m.Article.publisher,
            m.EntityMention.entity_id,
        )
        .join(m.Article, m.Article.id == m.EventArticle.article_id)
        .outerjoin(m.EntityMention, m.EntityMention.article_id == m.Article.id)
        .where(m.EventArticle.event_id.in_(list(event_ids)))
    )
    out: dict[int, dict[str, set[Any]]] = {}
    for event_id, publisher, entity_id in session.execute(stmt).all():
        bucket = out.setdefault(event_id, {"publishers": set(), "entity_ids": set()})
        if publisher:
            bucket["publishers"].add(publisher)
        if entity_id is not None:
            bucket["entity_ids"].add(entity_id)
    return out


def _reason(event: Any, thresholds: dict[str, float], linked: dict[str, set[Any]]) -> str:
    bits = [f"event type '{event.event_type}' matched watchlist filters"]
    if event.novelty_score is not None:
        bits.append(
            f"novelty {event.novelty_score:.2f} >= {thresholds['min_novelty']:.2f}"
        )
    if event.confidence is not None:
        bits.append(
            f"confidence {event.confidence:.2f} >= {thresholds['min_confidence']:.2f}"
        )
    publishers = sorted(linked.get("publishers") or [])
    if publishers:
        bits.append(f"publishers {', '.join(publishers[:3])}")
    return "; ".join(bits)


def _hash_reason(reason: str) -> str:
    import hashlib

    return hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]


def _touch(session: Session, watchlist_id: int, when: Any) -> None:
    obj = session.get(m.Watchlist, watchlist_id)
    if obj is not None:
        obj.last_evaluated_at = when


def evaluate_active_watchlists(
    session: Session, *, settings: Settings | None = None, now: Any | None = None
) -> list[EvaluationOutcome]:
    """Evaluate every active watchlist. Used by the worker's alert stage."""
    from app.db.repositories import WatchlistRepository

    repo = WatchlistRepository(session)
    outcomes: list[EvaluationOutcome] = []
    for watchlist in repo.list(active_only=True):
        outcomes.append(evaluate_watchlist(session, watchlist, settings=settings, now=now))
    return outcomes


__all__ = [
    "DEFAULT_THRESHOLDS",
    "EvaluationOutcome",
    "evaluate_active_watchlists",
    "evaluate_watchlist",
]
