"""Event endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._common import get_db

router = APIRouter()


@router.get("/")
def list_events(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    return {"events": [], "count": 0}


@router.get("/clusters")
def list_clusters(db: Session = Depends(get_db)):
    return {"clusters": []}


@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id: str, db: Session = Depends(get_db)):
    from naijafinsent.event_extraction import EventClusterer, event_timeline
    return {"cluster_id": cluster_id, "timeline": {"items": []}}


@router.get("/timeline")
def timeline(db: Session = Depends(get_db)):
    return {"timeline": [], "coverage_intensity": []}
