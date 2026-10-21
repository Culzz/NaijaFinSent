"""Request/response models for the API.

Two rules shape this module:

1. **Never redefine the core prediction schemas.** ``SentimentPrediction``,
   ``EntityPrediction``, ``EventPrediction``, ``AnalysisResult`` and friends are
   imported from ``naijafinsent.schemas`` and re-exported. Duplicating them here
   would let the API contract drift from the models that actually produce the
   values, which is the failure mode that makes a client silently wrong.

2. **Requests carry the guardrails.** Length limits, batch caps and encoding
   checks live on the request models, so validation happens before a request
   reaches the pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from naijafinsent.constants import (
    ENTITY_TYPES,
    EVENT_TYPES,
    SENTIMENT_LABELS,
    TRUST_TIERS,
)
from naijafinsent.schemas import (
    AnalysisResult,
    EntityPrediction,
    EntitySentimentPrediction,
    EntityType,
    EventCount,
    EventPrediction,
    EventType,
    EvidenceSpan,
    HealthStatus,
    ModelInfo,
    ModelRef,
    ProcessingStatus,
    SentimentLabel,
    SentimentPrediction,
    SentimentTrendPoint,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# Re-exports: the API's public contract IS the core contract.
# --------------------------------------------------------------------------
__all__ = [
    "AnalysisResult",
    "AlertItem",
    "AnalyzeRequest",
    "CopilotCitation",
    "CopilotRequest",
    "CopilotResponse",
    "EntityPrediction",
    "EntitySentimentPrediction",
    "EntityType",
    "ErrorResponse",
    "EventCount",
    "EventPrediction",
    "EventType",
    "EvidenceSpan",
    "HealthStatus",
    "LeaderboardEntry",
    "ModelInfo",
    "ModelRef",
    "NewsItem",
    "Page",
    "Pagination",
    "ProcessingStatus",
    "SentimentLabel",
    "SentimentPrediction",
    "SentimentRequest",
    "SentimentTrendPoint",
    "WatchlistCreate",
    "WatchlistEvaluation",
    "WatchlistOut",
]


# --------------------------------------------------------------------------
# Shared validation helpers
# --------------------------------------------------------------------------
def _check_text(value: str, *, field: str = "text") -> str:
    """Reject empty/whitespace-only text and control characters.

    Control characters (other than tab/newline) are rejected because they are
    almost always an encoding accident, and silently stripping them would make
    the persisted ``content_hash`` disagree with what the user submitted.
    """
    if value is None or not value.strip():
        raise ValueError(f"{field} must not be empty or whitespace-only")
    offenders = [c for c in value if ord(c) < 32 and c not in "\t\n\r"]
    if offenders:
        codes = sorted({ord(c) for c in offenders})
        raise ValueError(
            f"{field} contains control characters (codes {codes}); "
            "send clean UTF-8 text"
        )
    return value


class _TextPayload(BaseModel):
    """Base for models accepting either a single ``text`` or a ``texts`` batch."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(
        default=None,
        description="A single piece of text to analyse.",
        examples=["CBN raised the MPR by 200bps to 26.75%."],
    )
    texts: list[str] | None = Field(
        default=None,
        description="A batch of texts. Capped by the server's max batch size.",
    )

    @field_validator("text")
    @classmethod
    def _v_text(cls, v: str | None) -> str | None:
        return _check_text(v) if v is not None else None

    @field_validator("texts")
    @classmethod
    def _v_texts(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for i, item in enumerate(v):
            _check_text(item, field=f"texts[{i}]")
        return v

    def resolve_texts(self, *, max_text_chars: int, max_batch_size: int) -> list[str]:
        """Validate the payload shape and return the concrete list of texts.

        Raises ``ValueError`` with a human-readable message; the router converts
        that into the standard error envelope.
        """
        if self.text is not None and self.texts is not None:
            raise ValueError("provide either 'text' or 'texts', not both")
        if self.text is None and not self.texts:
            raise ValueError("provide 'text' or a non-empty 'texts' array")

        items = [self.text] if self.text is not None else list(self.texts or [])
        if len(items) > max_batch_size:
            raise ValueError(
                f"batch size {len(items)} exceeds the maximum of {max_batch_size}"
            )
        for i, item in enumerate(items):
            if len(item) > max_text_chars:
                raise ValueError(
                    f"text at index {i} is {len(item)} characters, "
                    f"which exceeds the maximum of {max_text_chars}"
                )
        return items


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
class SentimentRequest(_TextPayload):
    """Document-level sentiment request."""


class EntityRequest(_TextPayload):
    """Named-entity recognition request."""


class AnalyzeRequest(_TextPayload):
    """Full-pipeline analysis request (sentiment + entities + events)."""


class CopilotRequest(BaseModel):
    """Evidence-cited question over the stored corpus."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20, description="Retrieved passages to consider.")
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Drop retrieved passages below this relevance score.",
    )
    date_from: date | None = None
    date_to: date | None = None
    publisher: str | None = None
    allow_abstention: bool = Field(
        default=True,
        description="If True, the answer abstains when evidence is insufficient "
        "instead of guessing.",
    )

    @field_validator("question")
    @classmethod
    def _v_question(cls, v: str) -> str:
        return _check_text(v, field="question")


class WatchlistCreate(BaseModel):
    """Create a watchlist of transparent filters + thresholds."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner: str | None = None
    event_types: list[str] = Field(default_factory=list)
    entity_ids: list[int] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    min_novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sentiment_labels: list[str] = Field(default_factory=list)
    notify_on: str = Field(default="event", description="event | article")
    lookback_days: int = Field(default=7, ge=1, le=365)

    @field_validator("event_types")
    @classmethod
    def _v_event_types(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in EVENT_TYPES]
        if bad:
            raise ValueError(f"unknown event types {bad}; expected one of {list(EVENT_TYPES)}")
        return v

    @field_validator("sentiment_labels")
    @classmethod
    def _v_labels(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in SENTIMENT_LABELS]
        if bad:
            raise ValueError(f"unknown labels {bad}; expected one of {list(SENTIMENT_LABELS)}")
        return v


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """The single error envelope every failure path returns.

    ``request_id`` is what makes a user report actionable: it ties the message a
    client saw to the exact log line the server emitted.
    """

    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str | None = None
    code: str = "error"
    request_id: str | None = None
    status_code: int = 400
    disclaimer: str | None = Field(
        default=None, description="Present on every response that contains analysis."
    )


class Pagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    limit: int
    offset: int
    page: int = 1
    pages: int = 1
    has_next: bool = False


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Generic pagination envelope used by every list endpoint."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    pagination: Pagination


class NewsItem(BaseModel):
    """An article as the API exposes it.

    Note there is no ``content`` field. Per the legal data policy the API serves
    metadata and labels, and the URL a reader can visit; article bodies are not
    republished.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    url: str
    canonical_url: str | None = None
    title: str
    publisher: str
    source_id: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    language: str = "en"
    is_official_release: bool = False
    is_duplicate: bool = False
    word_count: int | None = None
    sentiment: SentimentPrediction | None = None
    content_retained: bool = Field(
        default=False,
        description="True only when the source licence permits storing the body.",
    )


class AlertItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    watchlist_id: int
    event_id: int | None = None
    article_id: int | None = None
    threshold: float | None = None
    score: float | None = None
    reason: str | None = None
    dedup_key: str
    created_at: datetime | None = None
    delivered_at: datetime | None = None


class WatchlistOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    owner: str | None = None
    is_active: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)
    last_evaluated_at: datetime | None = None
    created_at: datetime | None = None


class WatchlistEvaluation(BaseModel):
    """Result of evaluating a watchlist: the transparent record of what fired."""

    model_config = ConfigDict(extra="forbid")

    watchlist_id: int
    evaluated_at: datetime
    candidates: int = Field(description="Events/articles that matched the filters.")
    created: int = Field(description="New alerts actually written after dedup.")
    suppressed: int = Field(description="Matches suppressed as already-alerted.")
    alerts: list[AlertItem] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(
        default_factory=dict, description="The exact thresholds applied, for transparency."
    )
    disclaimer: str | None = None


class CopilotCitation(BaseModel):
    """A retrieved passage backing an answer. Answers may ONLY cite these."""

    model_config = ConfigDict(extra="forbid")

    article_id: int
    url: str
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    quote: str = Field(description="Verbatim excerpt from the source.")
    score: float = Field(ge=0.0, description="Retrieval relevance score.")
    method: str = Field(default="lexical", description="lexical | embedding | hybrid")


class CopilotResponse(BaseModel):
    """An evidence-cited answer, or an honest abstention."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    abstained: bool = Field(
        default=False,
        description="True when the evidence was insufficient and no answer was asserted.",
    )
    abstention_reason: str | None = None
    dropped_claims: list[str] = Field(
        default_factory=list,
        description="Sentences removed by the verifier because no citation supported them.",
    )
    retrieved: int = Field(default=0, description="Passages retrieved before filtering.")
    status: ProcessingStatus = ProcessingStatus.COMPLETE
    latency_ms: float | None = None
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str | None = None


class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    task: str
    split: str
    metrics: dict[str, float] = Field(default_factory=dict)
    version: str | None = None
    git_sha: str | None = None
    created_at: datetime | None = None


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: int = 0
    latest: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None
    disclaimer: str | None = None


# Keep the label-space contract visible to the schemas module's consumers.
__all__ += ["ENTITY_TYPES", "TRUST_TIERS"]
