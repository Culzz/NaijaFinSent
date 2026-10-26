"""Event endpoints, backed by the repository layer."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_novelty: float | None = None,
):
    repo = repositories.Repositories(db)
    rows, total = repo.events.list_events(
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        min_novelty=min_novelty,
        limit=limit,
        offset=offset,
    )
    return {"events": rows, "count": len(rows), "total": total}


@router.get("/clusters")
def list_clusters(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """Cluster view = primary events only (dedup collapses repeats at ingest)."""
    repo = repositories.Repositories(db)
    rows, total = repo.events.list_events(primary_only=True, limit=limit)
    return {"clusters": rows, "count": len(rows), "total": total}


@router.get("/stats/new-vs-repeated")
def new_vs_repeated(db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    return repo.events.new_vs_repeated()


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    event = repo.events.get_with_articles(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/{event_id}/timeline")
def event_timeline(event_id: int, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    items = repo.events.timeline(event_id)
    return {"event_id": event_id, "timeline": items}
