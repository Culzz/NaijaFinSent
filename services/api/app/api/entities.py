"""Entity endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._common import get_db

router = APIRouter()


@router.get("/")
def list_entities(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    return {"entities": [], "count": 0}


@router.get("/{entity_id}")
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    return {"entity_id": entity_id, "events": [], "timeline": []}


@router.get("/{entity_id}/timeline")
def entity_timeline(entity_id: str, db: Session = Depends(get_db)):
    from naijafinsent.event_extraction import entity_timeline as build_timeline
    return build_timeline(entity_id, [])
