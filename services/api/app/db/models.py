"""SQLAlchemy 2.0 models for the NaijaFinSent corpus, events and analytics store.

Blueprint fidelity
------------------
The table set here is exactly the one named in the blueprint. Every table and
column is documented because several columns encode *policy*, not just data:

Legal data policy (see ``docs/DEPLOYMENT.md`` and the data card)
    We store article **metadata, labels and hashed text**, not full article
    bodies, unless a source's licence explicitly permits retention. That is why
    ``articles.content`` is nullable with a default of ``None``: the pipeline
    operates on text at fetch time and persists the derived labels plus a
    ``content_hash``. Re-ingestion uses the hash to detect edits.

Aggregates are *news coverage measurements*
    ``sentiment_predictions`` rows are model outputs about **language in
    published coverage**. Nothing here measures investor sentiment, and nothing
    here supports a causal or predictive claim about prices. Any market series
    in ``market_observations`` is a **temporal association only** and requires
    authorised data to populate.

Three separate event dates
    ``financial_events`` keeps ``event_date`` (when it happened),
    ``publish_date`` (when it was reported) and ``processing_date`` (when *we*
    handled it) as three distinct columns. Collapsing them is the single most
    common way event studies silently become wrong.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from naijafinsent.utils import utcnow
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Shared JSON column type. ``JSON`` works on both SQLite (as TEXT with a
# serializer) and Postgres (jsonb-ish); we keep the portable variant.
JsonDict = JSON

# --------------------------------------------------------------------------
# Vocabularies kept as plain strings to avoid DB enum migrations. The
# authoritative lists live in ``naijafinsent.constants`` and are asserted
# against the pydantic enums in ``naijafinsent.schemas``.
# --------------------------------------------------------------------------
EVENT_ARTICLE_RELATIONS: tuple[str, ...] = ("originates", "repeats", "updates")
MARKET_SERIES: tuple[str, ...] = ("ngx_asi", "fx_ngn_usd", "mpr")


class TimestampMixin:
    """``created_at`` / ``updated_at`` with server-side defaults.

    Server defaults (not Python defaults) so that rows inserted by the worker,
    a migration, or a human in psql all get sane timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=utcnow,
    )


# ==========================================================================
# Corpus
# ==========================================================================


class Article(Base, TimestampMixin):
    """A fetched article: provenance metadata plus derived labels.

    ``content`` is NULL by default. See the module docstring: we persist labels
    and URLs, and retain full text only where the source licence permits it.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="Stable slug from the source manifest"
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="sha256 of normalised content"
    )
    # --- Legal policy -----------------------------------------------------
    # Full text is OPTIONAL. Default NULL: we store the hash + labels + URL.
    # Only populated when the source manifest's license_note permits retention.
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Full extracted text. NULL unless the source licence permits retention.",
    )
    is_official_release: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="CBN/SEC/NGX primary release"
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    ingest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    versions: Mapped[list[ArticleVersion]] = relationship(
        back_populates="article", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_articles_published_publisher", "published_at", "publisher"),
        Index("ix_articles_dup_hash", "content_hash", "is_duplicate"),
    )


class ArticleVersion(Base):
    """A snapshot marker for a URL we have fetched more than once.

    Live news pages get silently edited (corrections, added paragraphs, changed
    headlines). Without this table the corpus looks stable when it is not, and
    an annotation made against Tuesday's text may not match Friday's article.
    """

    __tablename__ = "article_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    change_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="first_seen",
        comment="first_seen | unchanged | edited | title_changed | body_changed",
    )
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    article: Mapped[Article] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("article_id", "content_hash", name="uq_article_version_hash"),
    )


# ==========================================================================
# Entities
# ==========================================================================


class Entity(Base, TimestampMixin):
    """A canonical real-world entity (company, person, regulator, sector...).

    ``valid_from`` / ``valid_to`` matter enormously for Nigerian corporate data:
    banks merge, tickers are retired, and "Diamond Bank" is the correct answer
    for a 2017 article while "Access Corporation" is correct for 2024. Point-in-
    time correctness depends on these two columns.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    primary_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="ORG | PER | REGULATOR | SECTOR | ..."
    )
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True, default="NG")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="NULL = still current. Set on merger/rename/delisting."
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # ``metadata`` is reserved by SQLAlchemy's declarative API, hence the name.
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JsonDict, nullable=True, default=dict
    )

    aliases: Mapped[list[EntityAlias]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", passive_deletes=True
    )
    mentions: Mapped[list[EntityMention]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", passive_deletes=True
    )


class EntityAlias(Base, TimestampMixin):
    """A surface form that resolves to a canonical :class:`Entity`.

    Covers legal names, abbreviations, tickers and the 3-5 spelling variants
    that Nigerian financial reporting genuinely produces ("GTBank", "GTCO",
    "Guaranty Trust Holding Company Plc").
    """

    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias_normalised: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="lowercased, punctuation-stripped"
    )
    alias_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="name",
        comment="legal_name | abbreviation | ticker | former_name | nickname",
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)

    entity: Mapped[Entity] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("entity_id", "alias_normalised", name="uq_entity_alias"),
    )


class EntityMention(Base, TimestampMixin):
    """A span in an article that refers to an entity.

    ``entity_id`` is NULLABLE on purpose: an unresolved or genuinely ambiguous
    mention is recorded as such rather than force-linked to the wrong company.
    Downstream precision metrics depend on being able to say "we did not know".
    """

    __tablename__ = "entity_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL = unresolved or ambiguous. Never guess.",
    )
    surface_form: Mapped[str] = mapped_column(String(512), nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mention_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ORG", comment="Primary entity type of the span"
    )
    resolution_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="alias | fuzzy | embedding | ambiguous | none"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sentence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inference_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    entity: Mapped[Entity | None] = relationship(back_populates="mentions")

    __table_args__ = (
        Index("ix_entity_mentions_entity", "entity_id", "article_id"),
        Index("ix_entity_mentions_article", "article_id"),
    )


# ==========================================================================
# Predictions
# ==========================================================================


class SentimentPredictionRow(Base, TimestampMixin):
    """A stored sentiment / entity-sentiment prediction.

    **Interpretation contract.** These rows are *news coverage measurements*:
    they describe the polarity of language in published articles. They are NOT
    a measurement of investor sentiment, positioning, or expectation, and no
    aggregate of this table supports a causal or predictive claim about prices
    or returns. The API surfaces this text in ``LIMITATIONS`` alongside results.

    ``article_id`` and ``entity_id`` are both nullable because the same table
    serves three shapes: a pure API call (no article), a document label
    (article, no entity) and a target-specific label (article + entity).
    """

    __tablename__ = "sentiment_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="sentiment",
        comment="sentiment = document level | entity_sentiment = target specific",
    )
    label: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True, comment="positive|negative|neutral|uncertain"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    probabilities: Mapped[dict[str, Any] | None] = mapped_column(
        JsonDict, nullable=True, default=dict
    )
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JsonDict, nullable=True, default=list, comment="Spans that justify the label"
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    inference_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_sentiment_article_task", "article_id", "task"),
        Index("ix_sentiment_entity_task", "entity_id", "task"),
    )


# ==========================================================================
# Events
# ==========================================================================


class FinancialEvent(Base, TimestampMixin):
    """An extracted financial event, modelled as a *cluster* of articles.

    Three dates, deliberately distinct (see module docstring):
      * ``event_date``      - when the thing happened in the world
      * ``publish_date``    - when the earliest reporting appeared
      * ``processing_date`` - when our pipeline processed it
    Lead time and look-ahead-bias audits are only possible with all three.

    ``cluster_id`` self-FK groups near-duplicate coverage of one real-world
    event; ``is_primary`` marks the canonical row a reader should be shown.
    """

    __tablename__ = "financial_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="One of naijafinsent.constants.EVENT_TYPES"
    )
    event_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Date of the event itself (may be NULL if only reported)"
    )
    publish_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Date the event was first reported"
    )
    processing_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=lambda: utcnow().date(), comment="Date WE processed it"
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(
        JsonDict, nullable=True, default=dict, comment="Typed slots: amount, currency, counterparty"
    )
    entities_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JsonDict, nullable=True, default=list, comment="Resolved entities attached to the event"
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Points at the cluster representative event",
    )
    novelty_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="1.0 = first report, lower = largely repeats known facts"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Canonical row for its cluster"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    inference_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    links: Mapped[list[EventArticle]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="EventArticle.event_id",
    )
    changes: Mapped[list[EventChange]] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_events_type_date", "event_type", "event_date"),
        Index("ix_events_publish_date", "publish_date"),
    )


class EventArticle(Base):
    """Join table: which article(s) evidence an event, and in what relation.

    ``relation`` distinguishes the article that broke the story from ones that
    merely repeat or meaningfully update it. That distinction is what lets the
    API answer "new vs repeated" honestly.
    """

    __tablename__ = "event_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("financial_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation: Mapped[str] = mapped_column(
        String(16), nullable=False, default="originates", comment="originates | repeats | updates"
    )
    similarity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Similarity to the cluster representative"
    )
    whats_new: Mapped[list[str] | None] = mapped_column(
        JsonDict, nullable=True, default=list, comment="Facts this article adds over prior coverage"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event: Mapped[FinancialEvent] = relationship(back_populates="links", foreign_keys=[event_id])
    article: Mapped[Article] = relationship()

    __table_args__ = (
        UniqueConstraint("event_id", "article_id", name="uq_event_article"),
    )


class EventChange(Base):
    """The "what's new" audit trail for an evolving event.

    A dividend event becomes "dividend + amount confirmed + register closure
    date set". Each transition is a row here, so the UI can show *how* our
    understanding changed and when.
    """

    __tablename__ = "event_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("financial_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    change_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="update", comment="created | update | corrected | merged"
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event: Mapped[FinancialEvent] = relationship(back_populates="changes")


# ==========================================================================
# Models / runs / evaluation
# ==========================================================================


class ModelVersion(Base, TimestampMixin):
    """A registered model artifact, mirroring ``data/models/registry.json``.

    The DB row is the *serving* record; the JSON registry is what the loader
    reads at boot. ``is_active`` marks the version currently wired into the
    pipeline so historical predictions can be attributed to the right model.
    """

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(32), nullable=False, default="sklearn")
    path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True, default=dict)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_version"),)


class InferenceRun(Base):
    """One inference request, with stage-wise provenance for error attribution.

    ``stage_provenance`` records which pipeline stages ran and which failed, so
    a bad output can be blamed on parsing, NER, classification, event
    extraction or entity resolution instead of being a mystery blob.
    ``request_hash`` lets us dedupe/spot repeated identical requests without
    storing the request body (privacy + the legal data policy).
    """

    __tablename__ = "inference_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="complete", comment="pending|processing|complete|partial|failed"
    )
    endpoint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stage_provenance: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JsonDict, nullable=True, default=list
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class EvaluationRun(Base):
    """A reproducible evaluation run against a named split.

    ``git_sha`` + ``dataset_hash`` + ``seed`` together are what make a number
    trustworthy: without them a metric is an anecdote. The CI regression gate
    compares a fresh run against a stored baseline using these fields.
    """

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    split: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="train|dev|test_random|test_source|test_time"
    )
    task: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True, default=dict)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (Index("ix_eval_task_split", "task", "split"),)


# ==========================================================================
# Watchlists / alerts
# ==========================================================================


class Watchlist(Base, TimestampMixin):
    """A saved filter over events/articles plus its alert thresholds.

    ``filters`` is deliberately declarative JSON (event types, entities,
    publishers, keywords, thresholds) so a user can inspect exactly why an
    alert fired. No hidden model decides what you are told about.
    """

    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True, default=dict)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    alerts: Mapped[list[Alert]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", passive_deletes=True
    )


class Alert(Base):
    """A watchlist hit.

    ``dedup_key`` is UNIQUE: evaluating a watchlist twice must not spam the same
    notification. The key is derived from the watchlist + the matched thing +
    the threshold that fired, so a *changed* situation still produces a new
    alert while an unchanged one is suppressed.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="The transparent threshold that fired"
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    watchlist: Mapped[Watchlist] = relationship(back_populates="alerts")

    __table_args__ = (Index("ix_alerts_watchlist_created", "watchlist_id", "created_at"),)


# ==========================================================================
# Market context
# ==========================================================================


class MarketObservation(Base):
    """A market data point kept purely as context.

    **Temporal association, not causation.** These series are plotted *next to*
    coverage measurements so a reader can see that two things moved in the same
    window. Nothing in this table establishes that coverage caused a move, or
    that a label predicts a future move.

    Requiring authorised data: NGX All-Share, CBN FX and MPR series are only
    populated from sources whose terms permit redistribution. Absent that, the
    table stays empty and the UI shows "no market context configured" rather
    than scraping around the restriction.
    """

    __tablename__ = "market_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    series: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="ngx_asi | fx_ngn_usd | mpr"
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("date", "series", name="uq_market_obs_date_series"),)


__all__ = [
    "EVENT_ARTICLE_RELATIONS",
    "MARKET_SERIES",
    "Alert",
    "Article",
    "ArticleVersion",
    "Entity",
    "EntityAlias",
    "EntityMention",
    "EvaluationRun",
    "EventArticle",
    "EventChange",
    "FinancialEvent",
    "InferenceRun",
    "MarketObservation",
    "ModelVersion",
    "SentimentPredictionRow",
    "TimestampMixin",
    "Watchlist",
]
