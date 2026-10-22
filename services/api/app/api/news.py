"""News ingestion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


class IngestRequest(BaseModel):
    url: str | None = None
    rss_url: str | None = None
    text: str | None = None


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    return {"sources": repositories.list_sources(db)}


@router.post("/ingest")
def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    if not any([req.url, req.rss_url, req.text]):
        raise HTTPException(status_code=400, detail="Provide url, rss_url, or text")
    # Stub implementation: the full ingestor lives in naijafinsent.data.ingest
    return {"status": "accepted", "message": "Ingestion queued (demo mode)"}


@router.get("/articles")
def list_articles(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    articles = repositories.list_articles(db, limit=limit)
    return {"articles": articles, "count": len(articles)}
