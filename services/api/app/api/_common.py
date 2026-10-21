"""Shared helpers for the API routers: validation, error envelopes, run recording."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from naijafinsent.config import Settings
from naijafinsent.schemas import SentimentPrediction
from naijafinsent.utils import sha256_text, utcnow

from services.api.app.schemas import ErrorResponse


class ValidationFailure(HTTPException):
    """A 422 with the standard error envelope pre-filled.

    FastAPI's default validation error has a different shape from our envelope,
    which would force every client to handle two formats. Routers raise this
    instead so there is exactly one error shape.
    """

    def __init__(self, detail: str, *, code: str = "validation_error", request: Request | None = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )
        self.code = code
        self.request_id = getattr(request.state, "request_id", None) if request else None


def error_envelope(
    *,
    message: str,
    detail: str | None,
    code: str,
    status_code: int,
    request_id: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build the single error body used by every failure path."""
    from naijafinsent.config import get_settings

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
    """Wrap a single prediction with status + disclaimer for the API surface."""
    return {
        "prediction": prediction.model_dump(mode="json"),
        "status": "complete",
        "disclaimer": settings.disclaimer,
    }


def request_fingerprint(text: str) -> str:
    """Hash a request body for dedup/observability without storing the text."""
    return sha256_text(text)[:32]


def now_iso() -> str:
    return utcnow().isoformat()


__all__ = [
    "ValidationFailure",
    "error_envelope",
    "now_iso",
    "prediction_response",
    "request_fingerprint",
]
