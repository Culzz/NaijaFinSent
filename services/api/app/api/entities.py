"""Entity endpoints, backed by the repository layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_entities(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    q: str | None = None,
):
    repo = repositories.Repositories(db)
    if q:
        rows = repo.entities.search(q, limit=limit)
        return {"entities": rows, "count": len(rows)}
    rows = repo.entities.list_entities(limit=limit)
    return {"entities": rows, "count": len(rows)}


@router.get("/search")
def search_entities(q: str, db: Session = Depends(get_db), limit: int = 20):
    repo = repositories.Repositories(db)
    return {"entities": repo.entities.search(q, limit=limit)}


@router.get("/{entity_id}")
def get_entity(entity_id: int, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    entity = repo.entities.get_with_relations(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/{entity_id}/timeline")
def entity_timeline(entity_id: int, db: Session = Depends(get_db), limit: int = 20):
    repo = repositories.Repositories(db)
    base = repo.entities.get(entity_id)
    if not base:
        raise HTTPException(status_code=404, detail="Entity not found")
    events = repo.entities.related_events(entity_id, limit=limit)
    trend = repo.entities.sentiment_trend(entity_id)
    return {
        "entity": base,
        "events": events,
        "coverage_sentiment": trend,
        "caveat": "Coverage language only — temporal association, not causation; "
        "not investment advice.",
    }
