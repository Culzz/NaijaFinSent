"""Watchlist + alert endpoints, backed by the repository layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


class WatchlistCreate(BaseModel):
    name: str
    entities: list[str] = []
    keywords: list[str] = []


@router.get("/")
def list_watchlists(db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    return {"watchlists": repo.watchlists.list()}


@router.post("/")
def create_watchlist(req: WatchlistCreate, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    existing = repo.watchlists.get_by_name(req.name)
    if existing:
        raise HTTPException(status_code=409, detail="Watchlist name already exists")
    return repo.watchlists.create(
        name=req.name,
        filters={"entities": req.entities, "keywords": req.keywords},
    )


@router.delete("/{watchlist_id}")
def delete_watchlist(watchlist_id: int, db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    ok = repo.watchlists.delete(watchlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return {"deleted": True}
