"""Model-registry endpoints, backed by the repository layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories

router = APIRouter()


@router.get("/")
def list_models(db: Session = Depends(get_db)):
    repo = repositories.Repositories(db)
    return {"models": repo.models.list()}


@router.get("/evaluations")
def latest_evaluations(
    db: Session = Depends(get_db),
    limit: int = 20,
):
    repo = repositories.Repositories(db)
    return {"evaluations": repo.runs.latest_evaluations(limit=limit)}
