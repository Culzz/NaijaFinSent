"""Health endpoints."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health():
    return {"status": "ok", "service": "naijafinsent-api"}


@router.get("/ready")
def ready():
    return {"status": "ready"}
