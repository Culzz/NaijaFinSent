"""NaijaFinSent FastAPI application.

All routes are versioned under /api/v1. The app is designed to run in a
fully-offline demo mode with deterministic fallbacks; heavier models are
loaded lazily via :mod:`app.services.model_loader`.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import inference
from app.api import articles, calendar, entities, events, health, models, news, notifications, watchlists
from app.db.base import engine
from app.db import models as db_models

app = FastAPI(
    title="NaijaFinSent API",
    description="Nigeria-focused financial NLP and event-intelligence platform.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS defaults are permissive for local dev only; tighten in production.
allowed = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables in dev/demo. Migrations (Alembic) exist for prod.
try:
    db_models.Base.metadata.create_all(bind=engine)
except Exception:  # noqa: BLE001 - DB may not be configured
    pass


@app.get("/")
def root():
    return {
        "name": "NaijaFinSent API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(articles.router, prefix="/api/v1/articles", tags=["articles"])
app.include_router(entities.router, prefix="/api/v1/entities", tags=["entities"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(calendar.router, prefix="/api/v1/calendar", tags=["calendar"])
app.include_router(inference.router, prefix="/api/v1/inference", tags=["inference"])
app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
app.include_router(watchlists.router, prefix="/api/v1/watchlists", tags=["watchlists"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])


__all__ = ["app"]
