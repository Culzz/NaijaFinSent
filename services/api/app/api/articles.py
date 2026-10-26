"""Article endpoints, backed by the repository layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_articles(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    publisher: str | None = None,
    sentiment: str | None = None,
    event_type: str | None = None,
    include_duplicates: bool = True,
):
    repo = repositories.Repositories(db)
    rows, total = repo.articles.list_filtered(
        limit=limit,
        offset=offset,
        q=q,
        publisher=publisher,
        sentiment=sentiment,
        event_type=event_type,
        include_duplicates=include_duplicates,
    )
    return {"articles": rows, "count": len(rows), "total": total}


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    article = repo.articles.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
