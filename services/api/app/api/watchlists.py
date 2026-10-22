"""Watchlists endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
_watchlists: list = []


class WatchlistCreate(BaseModel):
    name: str
    entities: list[str] = []
    keywords: list[str] = []


@router.get("/")
def list_watchlists():
    return {"watchlists": _watchlists}


@router.post("/")
def create_watchlist(req: WatchlistCreate):
    wl = {"id": f"wl-{len(_watchlists)+1:03d}", **req.model_dump()}
    _watchlists.append(wl)
    return wl
