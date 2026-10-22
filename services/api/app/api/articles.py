"""Article endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_articles(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    articles = repositories.list_articles(db, limit=limit)
    return {"articles": articles, "count": len(articles)}


@router.get("/{article_id}")
def get_article(article_id: str, db: Session = Depends(get_db)):
    article = repositories.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
