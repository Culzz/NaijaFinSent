"""Shared helpers for the API routers."""
from __future__ import annotations

from typing import Any, Generator

from fastapi import HTTPException, Request, status
from naijafinsent.config import Settings, get_settings
from naijafinsent.schemas import SentimentPrediction
from naijafinsent.utils import sha256_text, utcnow

from app.db.base import SessionLocal
from app.schemas import ErrorResponse


class ValidationFailure(HTTPException):
    """A 422 with the standard error envelope pre-filled."""

    def __init__(self, detail: str, *, code: str = "validation_error", request: Request | None = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )
        self.code = code
        self.request_id = getattr(request.state, "request_id", None) if request else None


def get_db() -> Generator:
    """One session per request; commits successful requests, rolls back errors.

    Without the commit, write endpoints (watchlist create/delete, article
    upsert) would only flush into a doomed transaction — rows vanish the
    moment the request closes its session.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()


def error_envelope(
    *,
    message: str,
    detail: str | None,
    code: str,
    status_code: int,
    request_id: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    return ErrorResponse(
        error=message,
        detail=detail,
        code=code,
        request_id=request_id,
        status_code=status_code,
        disclaimer=settings.disclaimer if status_code < 500 else None,
    ).model_dump()


def prediction_response(prediction: SentimentPrediction, settings: Settings) -> dict[str, Any]:
    return {
        "prediction": prediction.model_dump(mode="json"),
        "status": "complete",
        "disclaimer": settings.disclaimer,
    }


def request_fingerprint(text: str) -> str:
    return sha256_text(text)[:32]


def now_iso() -> str:
    return utcnow().isoformat()


__all__ = [
    "ValidationFailure",
    "error_envelope",
    "get_db",
    "now_iso",
    "prediction_response",
    "request_fingerprint",
]
