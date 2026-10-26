"""FastAPI dependencies: pipeline singleton, DB session, auth, pagination, rate limiting.

Rate limiting note
------------------
The limiter here is an **in-process token bucket keyed by client IP**. That is
correct for a single instance and for tests, but it is not a security boundary
in a multi-instance deployment: two replicas each allow the full quota, and a
restart resets every bucket. Production should point ``RATE_LIMIT_BACKEND`` at a
shared store (Redis) or enforce limits at the edge/proxy. This is documented
rather than hidden because "we have rate limiting" is exactly the kind of claim
that should be falsifiable.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Query, Request, status
from naijafinsent.config import Settings, get_settings
from naijafinsent.inference.pipeline import AnalysisPipeline, StubPipeline
from sqlalchemy.orm import Session

from app.db.base import get_db as _get_db_session
from app.db.repositories import Repositories


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def get_app_settings() -> Settings:
    """Settings dependency. Indirection here means tests can override it."""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
_pipeline_lock = threading.Lock()
_pipeline: AnalysisPipeline | None = None
_pipeline_info: dict[str, Any] = {}


def load_pipeline() -> tuple[AnalysisPipeline, dict[str, Any]]:
    """Build the serving pipeline once per process.

    Real models are loaded from ``settings.model_registry_path`` when it exists
    and is usable; otherwise we fall back to :class:`StubPipeline`. The fallback
    is deliberate and loud (it is recorded in ``_pipeline_info``), never silent:
    serving a stub while claiming to serve a model would be the worst outcome.
    """
    from app.services.model_loader import describe_memory_budget, load_pipeline_from_registry

    pipeline, info = load_pipeline_from_registry()
    info["memory_note"] = describe_memory_budget(pipeline)
    return pipeline, info


def get_pipeline() -> AnalysisPipeline:
    """Return the process-wide pipeline, building it on first use.

    Double-checked locking: a cold start can receive concurrent requests, and
    loading a model twice would double memory and waste seconds.
    """
    global _pipeline, _pipeline_info
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline, _pipeline_info = load_pipeline()
    return _pipeline


def get_pipeline_info() -> dict[str, Any]:
    """Metadata about the loaded pipeline (used by ``/health`` and ``/models``)."""
    if _pipeline is None:
        get_pipeline()
    return dict(_pipeline_info)


def set_pipeline(pipeline: AnalysisPipeline, info: dict[str, Any] | None = None) -> None:
    """Install a pipeline explicitly. Tests and the lifespan hook use this."""
    global _pipeline, _pipeline_info
    with _pipeline_lock:
        _pipeline = pipeline
        _pipeline_info = info or {
            "source": "override",
            "stub": isinstance(pipeline, StubPipeline),
            "models": [
                {"name": r.name, "version": r.version, "task": r.task}
                for r in pipeline.describe_models()
            ],
        }


def reset_pipeline() -> None:
    global _pipeline, _pipeline_info
    with _pipeline_lock:
        _pipeline = None
        _pipeline_info = {}


PipelineDep = Annotated[AnalysisPipeline, Depends(get_pipeline)]


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def get_db() -> Session:  # noqa: ANN201 - mirrors the base helper for override points
    """Request-scoped DB session.

    Re-exported here so routers depend on ``app.deps`` and tests can
    override exactly one symbol.
    """
    yield from _get_db_session()


DbDep = Annotated[Session, Depends(get_db)]


def get_repositories(session: DbDep) -> Repositories:
    """Bundle every repository for the request's session."""
    return Repositories(session)


RepoDep = Annotated[Repositories, Depends(get_repositories)]


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def require_api_key_if_configured(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """No-op unless an API key is configured.

    The platform is public-read by default, so this dependency exists to give a
    deployment a single switch to require a key without changing any router.
    Set ``NFS_API_KEY`` (or ``API_KEY``) to enable.
    """
    import os

    expected = os.environ.get("NFS_API_KEY") or os.environ.get("API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )


AuthDep = Depends(require_api_key_if_configured)


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------
@dataclass(slots=True)
class PaginationParams:
    limit: int
    offset: int

    @property
    def page(self) -> int:
        return (self.offset // self.limit) + 1 if self.limit else 1


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=200, description="Items per page.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip.")] = 0,
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]


def build_pagination(total: int, params: PaginationParams) -> dict[str, Any]:
    """Shape the ``pagination`` block of a :class:`Page` envelope."""
    pages = (total + params.limit - 1) // params.limit if params.limit else 0
    return {
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
        "page": params.page,
        "pages": pages,
        "has_next": params.offset + params.limit < total,
    }


# --------------------------------------------------------------------------
# Rate limiting (in-process token bucket)
# --------------------------------------------------------------------------
@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Token bucket keyed by client identity.

    ``capacity`` tokens refill linearly over one minute. A single request costs
    one token. Bursty but well-behaved clients are fine; a scraper is not.

    Thread-safe: FastAPI runs sync dependencies in a threadpool, so the dict is
    guarded by a lock.
    """

    def __init__(self, capacity: int, *, window_seconds: float = 60.0) -> None:
        self.capacity = max(1, capacity)
        self.window_seconds = window_seconds
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=float(self.capacity), updated_at=time.monotonic())
        )
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Consume a token. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        rate = self.capacity / self.window_seconds
        with self._lock:
            bucket = self._buckets[key]
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(float(self.capacity), bucket.tokens + elapsed * rate)
            bucket.updated_at = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            deficit = 1.0 - bucket.tokens
            return False, deficit / rate if rate > 0 else self.window_seconds

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_limiter: TokenBucketLimiter | None = None
_limiter_lock = threading.Lock()


def get_limiter() -> TokenBucketLimiter:
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = TokenBucketLimiter(get_settings().rate_limit_per_minute)
    return _limiter


def set_limiter(limiter: TokenBucketLimiter | None) -> None:
    """Swap the limiter (tests use a fresh bucket to avoid cross-test bleed)."""
    global _limiter
    _limiter = limiter


def _client_key(request: Request) -> str:
    """Identify the caller for rate limiting.

    ``X-Forwarded-For`` is honoured only for its first hop, which is correct
    behind a single trusted proxy. Without a proxy this header is attacker-
    controlled, so the limit is best-effort by design (see module docstring).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    """Dependency enforcing the configured per-minute limit."""
    limiter = get_limiter()
    allowed, retry_after = limiter.check(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"rate limit exceeded: {limiter.capacity} requests per "
                f"{int(limiter.window_seconds)}s"
            ),
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


RateLimitDep = Depends(rate_limit)


MY_KEY = "x-request-id"


def get_request_id(request: Request) -> str | None:
    """Request id set by the middleware, if the middleware ran."""
    return getattr(request.state, "request_id", None) or request.headers.get(MY_KEY)
