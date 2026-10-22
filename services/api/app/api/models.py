"""Models registry endpoints."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_models():
    return {
        "models": [
            {"name": "keyword-events", "task": "events", "version": "0.1.0", "status": "available"},
            {"name": "tfidf-events", "task": "events", "version": "0.1.0", "status": "available"},
            {"name": "keyword-ner", "task": "ner", "version": "0.1.0", "status": "available"},
        ]
    }


@router.get("/cards")
def model_cards():
    return {"cards": ["docs/MODEL_CARD.md"]}
