"""News surface: sources + analytics for the frontend dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    # Source manifests live in naijafinsent.data.sources; the corpus DB does not
    # keep a Source table, so we report the built-in manifest summary.
    from naijafinsent.data.sources import load_manifests

    try:
        entries = load_manifests()
        return {
            "sources": [
                {
                    "id": e.id,
                    "publisher": e.publisher,
                    "kind": e.kind,
                    "license_note": e.license_note,
                }
                for e in entries
            ]
        }
    except Exception:  # noqa: BLE001 - manifest is optional in demo mode
        return {"sources": []}


@router.get("/analytics/trends")
def analytics_trends(
    db: Session = Depends(get_db),
    granularity: str = "day",
):
    repo = repositories.Repositories(db)
    return {"trends": repo.analytics.sentiment_trend(granularity=granularity) if hasattr(repo.analytics, "sentiment_trend") else []}


@router.get("/analytics/event-counts")
def analytics_event_counts(db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    return {"event_counts": repo.analytics.event_counts()}


@router.get("/analytics/top-topics")
def analytics_top_topics(db: Session = Depends(get_db), limit: int = 10):
    repo = repositories.Repositories(db)
    return {"topics": repo.analytics.top_topics(limit=limit)}


@router.get("/analytics/freshness")
def analytics_freshness(db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    return repo.analytics.ingestion_freshness()
