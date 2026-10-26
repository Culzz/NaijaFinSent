"""Alert endpoints, backed by the repository layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_alerts(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
):
    repo = repositories.Repositories(db)
    return {"alerts": repo.watchlists.list_alerts(limit=limit)}


@router.post("/test")
def test_alert():
    return {"status": "ok", "message": "Alert dispatch path is wired at the worker level."}
