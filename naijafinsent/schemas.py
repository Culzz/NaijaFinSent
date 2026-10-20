"""Domain schemas shared across the core package, the API, and the worker.

Everything here is pure Pydantic — no DB, no web framework. The FastAPI layer
re-exports these, and the TypeScript client mirrors them field-for-field.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from naijafinsent.constants import (
    ENTITY_TYPES,
    EVENT_TYPES,
    SENTIMENT_LABELS,
)


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class EntityType(str, Enum):
    ORG = "ORG"
    PER = "PER"
    REGULATOR = "REGULATOR"
    MONEY = "MONEY"
    TICKER = "TICKER"
    CURRENCY = "CURRENCY"
    SECTOR = "SECTOR"
    EVENT_TRIGGER = "EVENT_TRIGGER"


class EventType(str, Enum):
    CBN_POLICY = "cbn_policy"
    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    MNA = "mna"
    REGULATORY_SANCTION = "regulatory_sanction"
    CAPITAL_RAISE = "capital_raise"
    FX_MOVE = "fx_move"
    OIL_ENERGY = "oil_energy"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"      # some pipeline stages failed
    FAILED = "failed"


# --------------------------------------------------------------------------
# Corpus / provenance
# --------------------------------------------------------------------------

class SourceManifestEntry(BaseModel):
    """A registered source, audited in Stage 0."""
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(description="Stable slug, e.g. 'businessday'")
    name: str
    base_url: str
    url_pattern: str = Field(description="How article URLs are recognised")
    access_method: str = Field(description="rss | sitemap | html | api")
    license_note: str = Field(description="What we may store/reuse, per audit")
    trust_tier: str = Field(description="official | tier1 | tier2 | tier3 | unknown")
    robots_checked_at: datetime | None = None
    enabled: bool = True
    notes: str | None = None


class Article(BaseModel):
    """A fetched, provenance-tracked article (metadata + text)."""
    model_config = ConfigDict(extra="forbid")

    article_id: str = Field(description="Content-addressed or DB id")
    url: str
    canonical_url: str | None = None
    title: str
    publisher: str
    source_id: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    language: str = "en"
    content: str = Field(description="Full extracted text (never published)")
    content_hash: str = Field(description="sha256 of normalised content")
    is_official_release: bool = False
    syndicated_from: str | None = Field(
        default=None, description="Original article_id if this is syndicated copy"
    )
    is_duplicate: bool = False
    duplicate_of: str | None = None
    minhash_signature: list[int] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Annotation
# --------------------------------------------------------------------------

class EntitySpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str
    entity_type: EntityType

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start", 0)
        if v <= start:
            raise ValueError("end must be > start")
        return v


class MoneyAnnotation(BaseModel):
    """Money normalisation: keep the original span, store value + ISO code.
    Never infer a missing unit."""
    model_config = ConfigDict(extra="forbid")

    span: EntitySpan
    value: float | None = None
    currency: str | None = Field(default=None, description="ISO 4217, e.g. NGN, USD")
    unit: str | None = Field(default=None, description="e.g. million, billion — only if stated")


class SentimentAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(default="sentiment", description="sentiment | entity_sentiment")
    label: SentimentLabel
    target_entity: str | None = Field(
        default=None, description="entity_id when task == entity_sentiment"
    )
    rationale_span: EntitySpan | None = None
    annotator: str = "unknown"
    model_prelabel: bool = Field(
        default=False, description="True if an LLM pre-labelled and a human reviewed"
    )


class EventAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    event_date: date | None = Field(
        default=None, description="Date the event happened, NOT the publish date"
    )
    entities: list[EntitySpan] = Field(default_factory=list)
    evidence_span: EntitySpan | None = Field(
        default=None, description="The text span that justifies the label"
    )
    annotator: str = "unknown"
    model_prelabel: bool = False


class AnnotationRecord(BaseModel):
    """One annotated item, exportable from Label Studio / Doccano."""
    model_config = ConfigDict(extra="forbid")

    item_id: str
    article_id: str
    split: str = Field(description="train | dev | test_random | test_source | test_time")
    text: str
    sentiment: SentimentAnnotation | None = None
    spans: list[EntitySpan] = Field(default_factory=list)
    money: list[MoneyAnnotation] = Field(default_factory=list)
    events: list[EventAnnotation] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Predictions (every one carries evidence + model version)
# --------------------------------------------------------------------------

class EvidenceSpan(BaseModel):
    """A span of source text backing a prediction."""
    model_config = ConfigDict(extra="forbid")

    text: str
    start: int
    end: int


class ModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = "unknown"
    task: str
    calibrated: bool = False


class SentimentPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0, description="Calibrated when model.calibrated")
    probabilities: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    model: ModelRef


class EntityPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span: EntitySpan
    entity_id: str | None = Field(
        default=None, description="Resolved canonical entity; None = unresolved"
    )
    canonical_name: str | None = None
    resolution_method: str | None = Field(
        default=None, description="alias | fuzzy | embedding | ambiguous"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EntitySentimentPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None
    canonical_name: str | None
    label: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    model: ModelRef


class EventPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    confidence: float = Field(ge=0.0, le=1.0)
    event_date: date | None = None
    entities: list[EntityPrediction] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    model: ModelRef


class AnalysisResult(BaseModel):
    """Full pipeline output for one text. This is what /analyze returns."""
    model_config = ConfigDict(extra="forbid")

    text_sha256: str
    language: str = "en"
    status: ProcessingStatus
    sentiment: SentimentPrediction | None = None
    entities: list[EntityPrediction] = Field(default_factory=list)
    entity_sentiments: list[EntitySentimentPrediction] = Field(default_factory=list)
    events: list[EventPrediction] = Field(default_factory=list)
    limitations: list[str] = Field(
        default_factory=list,
        description="Honest caveats the UI must display alongside predictions",
    )
    processed_at: datetime
    latency_ms: float | None = None


# --------------------------------------------------------------------------
# Analytics shapes consumed by the frontend
# --------------------------------------------------------------------------

class SentimentTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str = Field(description="ISO date or YYYY-MM depending on granularity")
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    uncertain: int = 0
    mean_score: float | None = None


class EventCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    count: int


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    task: str
    framework: str = "sklearn"
    metrics: dict[str, float] = Field(default_factory=dict)
    trained_at: datetime | None = None
    description: str | None = None


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    database: str = "unknown"
    models_loaded: list[str] = Field(default_factory=list)
    corpus_size: int | None = None
    last_ingestion_at: datetime | None = None


# --------------------------------------------------------------------------
# Guard the label-space contracts stay in sync with constants
# --------------------------------------------------------------------------

assert tuple(m.value for m in SentimentLabel) == SENTIMENT_LABELS
assert tuple(m.value for m in EntityType) == ENTITY_TYPES
assert tuple(m.value for m in EventType) == EVENT_TYPES
