"""Notifications/alerts endpoints."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
_alerts: list = []


@router.get("/")
def list_alerts():
    return {"alerts": _alerts, "count": len(_alerts)}


@router.post("/test")
def test_alert():
    return {"status": "ok"}
