"""Query helpers over the ORM.

Why this module exists
----------------------
Routers should not contain SQL. Repositories here:

* return **plain dicts or pydantic models**, never live ORM instances, so a
  router cannot accidentally trigger a lazy load inside a closed session, and
  the JSON shape is explicit rather than "whatever the columns were today";
* push aggregation into the database (``GROUP BY``, ``COUNT``) instead of
  looping in Python, which is the difference between a 20ms and a 2s analytics
  endpoint;
* take an explicit ``Session`` so the worker, tests and the API all share one
  implementation.

Filters are always applied as real WHERE clauses, never post-filtered, so
pagination counts stay honest.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from naijafinsent.constants import EVENT_TYPES, SENTIMENT_LABELS
from sqlalchemy import Select, and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.app.db import models as m


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------
def _iso(value: Any) -> Any:
    """JSON-safe scalar: datetimes and dates become ISO strings, everything else passes."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row_to_dict(obj: Any, fields: Sequence[str]) -> dict[str, Any]:
    return {f: _iso(getattr(obj, f, None)) for f in fields}


ARTICLE_FIELDS: tuple[str, ...] = (
    "id",
    "url",
    "canonical_url",
    "title",
    "publisher",
    "source_id",
    "published_at",
    "fetched_at",
    "language",
    "content_hash",
    "is_official_release",
    "is_duplicate",
    "duplicate_of",
    "word_count",
    "ingest_run_id",
    "created_at",
)

EVENT_FIELDS: tuple[str, ...] = (
    "id",
    "event_type",
    "event_date",
    "publish_date",
    "processing_date",
    "title",
    "summary",
    "attributes",
    "cluster_id",
    "novelty_score",
    "is_primary",
    "confidence",
    "created_at",
)

ENTITY_FIELDS: tuple[str, ...] = (
    "id",
    "canonical_name",
    "primary_type",
    "ticker",
    "sector",
    "country",
    "valid_from",
    "valid_to",
    "is_active",
)


def _granularity_expr(granularity: str, column: Any) -> Any:
    """Build a portable date-truncation expression.

    SQLite and Postgres disagree on ``date_trunc`` / ``strftime``, so we branch
    on the dialect rather than emitting dialect-specific SQL blindly. Anything
    other than day/week/month falls back to day.
    """
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}.get(granularity, "%Y-%m-%d")
    dialect = column.class_.__table__.metadata.bind.dialect.name if False else None
    # We detect at call time from the session bind instead (see callers), so
    # keep a small helper that works on both engines using func.strftime with a
    # Postgres fallback string built from the same format.
    _ = dialect
    return fmt


def _period_expr(dialect: str, column: Any, granularity: str) -> Any:
    """Return a SQL expression producing the bucket label for a datetime column."""
    if dialect == "sqlite":
        fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}.get(granularity)
        if fmt is None:
            fmt = "%Y-%m-%d"
        return func.strftime(fmt, column)
    # Postgres (and anything else with date_trunc).
    unit = granularity if granularity in {"day", "week", "month"} else "day"
    return func.to_char(func.date_trunc(unit, column), "YYYY-MM-DD" if unit == "day" else (
        "IYYY-IW" if unit == "week" else "YYYY-MM"
    ))


# ==========================================================================
# Articles
# ==========================================================================
class ArticleRepository:
    """CRUD + filtered listing for ``articles``."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, article_id: int) -> dict[str, Any] | None:
        obj = self.session.get(m.Article, article_id)
        return _row_to_dict(obj, ARTICLE_FIELDS) if obj else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        obj = self.session.scalar(select(m.Article).where(m.Article.url == url))
        return _row_to_dict(obj, ARTICLE_FIELDS) if obj else None

    def get_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        obj = self.session.scalar(
            select(m.Article).where(m.Article.content_hash == content_hash).limit(1)
        )
        return _row_to_dict(obj, ARTICLE_FIELDS) if obj else None

    def create(
        self,
        *,
        url: str,
        title: str,
        publisher: str,
        content_hash: str,
        published_at: datetime | None = None,
        canonical_url: str | None = None,
        source_id: str | None = None,
        language: str = "en",
        content: str | None = None,
        is_official_release: bool = False,
        ingest_run_id: str | None = None,
        word_count: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Insert an article. ``content`` stays ``None`` unless retention is permitted."""
        obj = m.Article(
            url=url,
            title=title,
            publisher=publisher,
            content_hash=content_hash,
            published_at=published_at,
            canonical_url=canonical_url,
            source_id=source_id,
            language=language,
            content=content,
            is_official_release=is_official_release,
            ingest_run_id=ingest_run_id,
            word_count=word_count,
            **extra,
        )
        self.session.add(obj)
        self.session.flush()
        return _row_to_dict(obj, ARTICLE_FIELDS)

    def upsert_by_url(self, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        """Insert or return the existing row for ``url``.

        Returns ``(article, created)``. Used by the ingest adapter so re-running
        ingestion is idempotent rather than a unique-constraint crash.
        """
        url = kwargs["url"]
        existing = self.session.scalar(select(m.Article).where(m.Article.url == url))
        if existing is not None:
            return _row_to_dict(existing, ARTICLE_FIELDS), False
        return self.create(**kwargs), True

    def update(self, article_id: int, **fields: Any) -> dict[str, Any] | None:
        obj = self.session.get(m.Article, article_id)
        if obj is None:
            return None
        for key, value in fields.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        self.session.flush()
        return _row_to_dict(obj, ARTICLE_FIELDS)

    def delete(self, article_id: int) -> bool:
        obj = self.session.get(m.Article, article_id)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.flush()
        return True

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(m.Article.id))) or 0)

    def _filtered_stmt(
        self,
        *,
        publisher: str | None = None,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
        entity_id: int | None = None,
        event_type: str | None = None,
        sentiment: str | None = None,
        q: str | None = None,
        include_duplicates: bool = True,
        source_id: str | None = None,
        is_official_release: bool | None = None,
    ) -> Select[Any]:
        """Compose the WHERE clause shared by listing and counting."""
        stmt = select(m.Article)
        conditions = []

        if publisher:
            conditions.append(m.Article.publisher == publisher)
        if source_id:
            conditions.append(m.Article.source_id == source_id)
        if is_official_release is not None:
            conditions.append(m.Article.is_official_release.is_(is_official_release))
        if date_from is not None:
            conditions.append(m.Article.published_at >= _as_dt(date_from))
        if date_to is not None:
            conditions.append(m.Article.published_at <= _as_dt(date_to, end_of_day=True))
        if not include_duplicates:
            conditions.append(m.Article.is_duplicate.is_(False))
        if q:
            # Portable case-insensitive contains across the two text columns.
            like = f"%{q.lower()}%"
            conditions.append(
                or_(
                    func.lower(m.Article.title).like(like),
                    func.lower(func.coalesce(m.Article.content, "")).like(like),
                    func.lower(m.Article.url).like(like),
                )
            )
        if sentiment:
            conditions.append(
                m.Article.id.in_(
                    select(m.SentimentPredictionRow.article_id).where(
                        m.SentimentPredictionRow.label == sentiment,
                        m.SentimentPredictionRow.task == "sentiment",
                        m.SentimentPredictionRow.article_id.is_not(None),
                    )
                )
            )
        if entity_id is not None:
            conditions.append(
                m.Article.id.in_(
                    select(m.EntityMention.article_id).where(
                        m.EntityMention.entity_id == entity_id
                    )
                )
            )
        if event_type:
            conditions.append(
                m.Article.id.in_(
                    select(m.EventArticle.article_id)
                    .join(m.FinancialEvent, m.FinancialEvent.id == m.EventArticle.event_id)
                    .where(m.FinancialEvent.event_type == event_type)
                )
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        return stmt

    def list_filtered(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "published_at",
        descending: bool = True,
        **filters: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return ``(rows, total)`` where ``total`` ignores limit/offset."""
        stmt = self._filtered_stmt(**filters)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.session.scalar(count_stmt) or 0)

        column = getattr(m.Article, order_by, m.Article.published_at)
        stmt = stmt.order_by(column.desc() if descending else column.asc(), m.Article.id.desc())
        stmt = stmt.limit(limit).offset(offset)

        rows = [_row_to_dict(o, ARTICLE_FIELDS) for o in self.session.scalars(stmt).all()]
        return rows, total


def _as_dt(value: datetime | date, *, end_of_day: bool = False) -> datetime:
    """Coerce a date to the start (or end) of that day for range comparisons."""
    if isinstance(value, datetime):
        return value
    if end_of_day:
        return datetime.combine(value, datetime.max.time())
    return datetime.combine(value, datetime.min.time())


# ==========================================================================
# Events
# ==========================================================================
class EventRepository:
    """Read helpers for ``financial_events`` and its cluster membership."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, event_id: int) -> dict[str, Any] | None:
        obj = self.session.get(m.FinancialEvent, event_id)
        if obj is None:
            return None
        data = _row_to_dict(obj, EVENT_FIELDS)
        data["article_count"] = int(
            self.session.scalar(
                select(func.count(m.EventArticle.id)).where(m.EventArticle.event_id == event_id)
            )
            or 0
        )
        return data

    def get_with_articles(self, event_id: int) -> dict[str, Any] | None:
        """Event + linked articles + change trail, in the shape ``/events/{id}`` returns."""
        event = self.get(event_id)
        if event is None:
            return None
        event["articles"] = self.linked_articles(event_id)
        event["changes"] = self.changes(event_id)
        event["timeline"] = self.timeline(event_id)
        return event

    def linked_articles(self, event_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(m.EventArticle, m.Article)
            .join(m.Article, m.Article.id == m.EventArticle.article_id)
            .where(m.EventArticle.event_id == event_id)
            .order_by(m.Article.published_at.asc().nulls_last(), m.Article.id.asc())
        )
        out: list[dict[str, Any]] = []
        for link, article in self.session.execute(stmt).all():
            row = _row_to_dict(article, ARTICLE_FIELDS)
            row.update(
                {
                    "relation": link.relation,
                    "similarity": link.similarity,
                    "whats_new": link.whats_new or [],
                }
            )
            out.append(row)
        return out

    def changes(self, event_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(m.EventChange)
            .where(m.EventChange.event_id == event_id)
            .order_by(m.EventChange.detected_at.asc(), m.EventChange.id.asc())
        )
        return [
            _row_to_dict(
                c,
                (
                    "id",
                    "event_id",
                    "change_type",
                    "field",
                    "old_value",
                    "new_value",
                    "source_article_id",
                    "detected_at",
                ),
            )
            for c in self.session.scalars(stmt).all()
        ]

    def timeline(self, event_id: int) -> list[dict[str, Any]]:
        """Coverage timeline: when the story broke and how it developed.

        Merges article links (with their relation) and field changes into one
        chronological list, which is what the UI renders.
        """
        points: list[dict[str, Any]] = []
        for row in self.linked_articles(event_id):
            points.append(
                {
                    "kind": "article",
                    "at": row.get("published_at") or row.get("fetched_at"),
                    "article_id": row["id"],
                    "publisher": row.get("publisher"),
                    "title": row.get("title"),
                    "relation": row["relation"],
                    "whats_new": row.get("whats_new", []),
                }
            )
        for change in self.changes(event_id):
            points.append(
                {
                    "kind": "change",
                    "at": change.get("detected_at"),
                    "field": change.get("field"),
                    "change_type": change.get("change_type"),
                    "old_value": change.get("old_value"),
                    "new_value": change.get("new_value"),
                    "article_id": change.get("source_article_id"),
                }
            )
        points.sort(key=lambda p: (p.get("at") is None, p.get("at") or ""))
        return points

    def list_events(
        self,
        *,
        event_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        entity_id: int | None = None,
        primary_only: bool = True,
        min_novelty: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(m.FinancialEvent)
        conditions = []
        if event_type:
            conditions.append(m.FinancialEvent.event_type == event_type)
        if primary_only:
            conditions.append(m.FinancialEvent.is_primary.is_(True))
        if date_from is not None:
            conditions.append(m.FinancialEvent.event_date >= date_from)
        if date_to is not None:
            conditions.append(m.FinancialEvent.event_date <= date_to)
        if min_novelty is not None:
            conditions.append(m.FinancialEvent.novelty_score >= min_novelty)
        if entity_id is not None:
            # Entities on an event are stored as JSON; match on the article links
            # too so this stays index-friendly for the common path.
            conditions.append(
                m.FinancialEvent.id.in_(
                    select(m.EventArticle.event_id)
                    .join(m.Article, m.Article.id == m.EventArticle.article_id)
                    .join(m.EntityMention, m.EntityMention.article_id == m.Article.id)
                    .where(m.EntityMention.entity_id == entity_id)
                )
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))

        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        stmt = stmt.order_by(
            m.FinancialEvent.processing_date.desc(),
            m.FinancialEvent.id.desc(),
        ).limit(limit).offset(offset)
        rows = [_row_to_dict(o, EVENT_FIELDS) for o in self.session.scalars(stmt).all()]
        return rows, total

    def new_vs_repeated(self, *, since: date | None = None) -> dict[str, int]:
        """Count events by novelty: genuinely new vs mostly-repeated coverage.

        The threshold is transparent and fixed at 0.5 rather than learned, so the
        number can be explained to a reader.
        """
        stmt = select(
            func.sum(case((m.FinancialEvent.novelty_score >= 0.5, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            m.FinancialEvent.novelty_score.is_not(None),
                            m.FinancialEvent.novelty_score < 0.5,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        if since is not None:
            stmt = stmt.where(m.FinancialEvent.processing_date >= since)
        new_count, repeated = self.session.execute(stmt).one()
        return {"new": int(new_count or 0), "repeated": int(repeated or 0)}


# ==========================================================================
# Entities
# ==========================================================================
class EntityRepository:
    """Entity lookup plus the aggregate views the entity page needs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: int) -> dict[str, Any] | None:
        obj = self.session.get(m.Entity, entity_id)
        return _row_to_dict(obj, ENTITY_FIELDS) if obj else None

    def get_with_relations(self, entity_id: int) -> dict[str, Any] | None:
        """Entity + aliases + mention summary + related events + sentiment trend."""
        data = self.get(entity_id)
        if data is None:
            return None
        data["aliases"] = self.aliases(entity_id)
        data["mention_count"] = self.mention_count(entity_id)
        data["recent_mentions"] = self.recent_mentions(entity_id, limit=20)
        data["related_events"] = self.related_events(entity_id, limit=20)
        data["sentiment_trend"] = self.sentiment_trend(entity_id, granularity="day")
        return data

    def aliases(self, entity_id: int) -> list[dict[str, Any]]:
        stmt = select(m.EntityAlias).where(m.EntityAlias.entity_id == entity_id)
        return [
            _row_to_dict(
                a,
                (
                    "id",
                    "alias",
                    "alias_normalised",
                    "alias_type",
                    "valid_from",
                    "valid_to",
                    "confidence",
                    "source",
                ),
            )
            for a in self.session.scalars(stmt).all()
        ]

    def mention_count(self, entity_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(m.EntityMention.id)).where(
                    m.EntityMention.entity_id == entity_id
                )
            )
            or 0
        )

    def recent_mentions(self, entity_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(m.EntityMention, m.Article)
            .join(m.Article, m.Article.id == m.EntityMention.article_id)
            .where(m.EntityMention.entity_id == entity_id)
            .order_by(m.Article.published_at.desc().nulls_last(), m.EntityMention.id.desc())
            .limit(limit)
        )
        out: list[dict[str, Any]] = []
        for mention, article in self.session.execute(stmt).all():
            out.append(
                {
                    "mention_id": mention.id,
                    "surface_form": mention.surface_form,
                    "mention_type": mention.mention_type,
                    "confidence": mention.confidence,
                    "resolution_method": mention.resolution_method,
                    "char_start": mention.char_start,
                    "char_end": mention.char_end,
                    "article_id": article.id,
                    "title": article.title,
                    "publisher": article.publisher,
                    "url": article.url,
                    "published_at": _iso(article.published_at),
                }
            )
        return out

    def related_events(self, entity_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(m.FinancialEvent)
            .where(
                m.FinancialEvent.id.in_(
                    select(m.EventArticle.event_id)
                    .join(m.Article, m.Article.id == m.EventArticle.article_id)
                    .join(m.EntityMention, m.EntityMention.article_id == m.Article.id)
                    .where(m.EntityMention.entity_id == entity_id)
                )
            )
            .order_by(m.FinancialEvent.processing_date.desc(), m.FinancialEvent.id.desc())
            .limit(limit)
        )
        return [_row_to_dict(o, EVENT_FIELDS) for o in self.session.scalars(stmt).all()]

    def sentiment_trend(
        self, entity_id: int, *, granularity: str = "day"
    ) -> list[dict[str, Any]]:
        """Entity-level sentiment over time (only ``entity_sentiment`` rows)."""
        dialect = self.session.bind.dialect.name if self.session.bind else "sqlite"
        period = _period_expr(dialect, m.Article.published_at, granularity).label("period")
        stmt = (
            select(
                period,
                func.sum(case((m.SentimentPredictionRow.label == "positive", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "negative", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "neutral", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "uncertain", 1), else_=0)),
                func.avg(m.SentimentPredictionRow.confidence),
            )
            .join(m.Article, m.Article.id == m.SentimentPredictionRow.article_id)
            .where(
                m.SentimentPredictionRow.entity_id == entity_id,
                m.SentimentPredictionRow.article_id.is_not(None),
            )
            .group_by(period)
            .order_by(period)
        )
        return [_trend_row(r) for r in self.session.execute(stmt).all()]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        stmt = (
            select(m.Entity)
            .where(
                or_(
                    func.lower(m.Entity.canonical_name).like(like),
                    func.lower(func.coalesce(m.Entity.ticker, "")).like(like),
                )
            )
            .order_by(m.Entity.canonical_name)
            .limit(limit)
        )
        return [_row_to_dict(o, ENTITY_FIELDS) for o in self.session.scalars(stmt).all()]

    def list_entities(
        self,
        *,
        primary_type: str | None = None,
        q: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(m.Entity)
        conditions = []
        if primary_type:
            conditions.append(m.Entity.primary_type == primary_type)
        if active_only:
            conditions.append(m.Entity.is_active.is_(True))
        if q:
            like = f"%{q.lower()}%"
            conditions.append(
                or_(
                    func.lower(m.Entity.canonical_name).like(like),
                    func.lower(func.coalesce(m.Entity.ticker, "")).like(like),
                    m.Entity.id.in_(
                        select(m.EntityAlias.entity_id).where(
                            func.lower(m.EntityAlias.alias).like(like)
                        )
                    ),
                )
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        total = int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        stmt = stmt.order_by(m.Entity.canonical_name.asc()).limit(limit).offset(offset)
        rows = [_row_to_dict(o, ENTITY_FIELDS) for o in self.session.scalars(stmt).all()]
        return rows, total

    def create(self, *, canonical_name: str, primary_type: str, **extra: Any) -> dict[str, Any]:
        obj = m.Entity(canonical_name=canonical_name, primary_type=primary_type, **extra)
        self.session.add(obj)
        self.session.flush()
        return _row_to_dict(obj, ENTITY_FIELDS)

    def add_alias(
        self, entity_id: int, alias: str, *, alias_type: str = "name", **extra: Any
    ) -> dict[str, Any]:
        from naijafinsent.utils import slugify

        obj = m.EntityAlias(
            entity_id=entity_id,
            alias=alias,
            alias_normalised=slugify(alias),
            alias_type=alias_type,
            **extra,
        )
        self.session.add(obj)
        self.session.flush()
        return _row_to_dict(obj, ("id", "entity_id", "alias", "alias_type"))


# ==========================================================================
# Analytics
# ==========================================================================
class AnalyticsRepository:
    """Aggregates the dashboard and ``/analytics/*`` endpoints read.

    All aggregation happens in SQL. Article sentiment is joined to the article
    only to bucket by publish date; the label itself comes from the prediction row.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _dialect(self) -> str:
        return self.session.bind.dialect.name if self.session.bind else "sqlite"

    def sentiment_trend(
        self,
        *,
        granularity: str = "day",
        publisher: str | None = None,
        entity_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        """Document-level sentiment counts bucketed by period.

        ``mean_score`` is the mean confidence of the winning label, a rough
        strength indicator — NOT a market signal.
        """
        period = _period_expr(self._dialect(), m.Article.published_at, granularity).label("period")
        stmt = (
            select(
                period,
                func.sum(case((m.SentimentPredictionRow.label == "positive", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "negative", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "neutral", 1), else_=0)),
                func.sum(case((m.SentimentPredictionRow.label == "uncertain", 1), else_=0)),
                func.avg(m.SentimentPredictionRow.confidence),
            )
            .join(m.Article, m.Article.id == m.SentimentPredictionRow.article_id)
            .where(
                m.SentimentPredictionRow.article_id.is_not(None),
                m.SentimentPredictionRow.task == "sentiment",
            )
        )
        if publisher:
            stmt = stmt.where(m.Article.publisher == publisher)
        if date_from is not None:
            stmt = stmt.where(m.Article.published_at >= _as_dt(date_from))
        if date_to is not None:
            stmt = stmt.where(m.Article.published_at <= _as_dt(date_to, end_of_day=True))
        if entity_id is not None:
            stmt = stmt.where(
                m.Article.id.in_(
                    select(m.EntityMention.article_id).where(
                        m.EntityMention.entity_id == entity_id
                    )
                )
            )
        stmt = stmt.group_by(period).order_by(period)
        return [_trend_row(r) for r in self.session.execute(stmt).all()]

    def event_counts(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        publisher: str | None = None,
    ) -> list[dict[str, Any]]:
        """Event totals per type, returned in taxonomy order so the UI is stable."""
        stmt = select(m.FinancialEvent.event_type, func.count(m.FinancialEvent.id))
        if date_from is not None:
            stmt = stmt.where(m.FinancialEvent.event_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(m.FinancialEvent.event_date <= date_to)
        if publisher:
            stmt = stmt.where(
                m.FinancialEvent.id.in_(
                    select(m.EventArticle.event_id)
                    .join(m.Article, m.Article.id == m.EventArticle.article_id)
                    .where(m.Article.publisher == publisher)
                )
            )
        stmt = stmt.group_by(m.FinancialEvent.event_type)
        counts = {row[0]: int(row[1]) for row in self.session.execute(stmt).all()}
        # Emit every taxonomy member, including zeros: a missing bar reads as a bug.
        return [{"event_type": et, "count": counts.get(et, 0)} for et in EVENT_TYPES]

    def top_topics(self, *, limit: int = 10, date_from: date | None = None) -> list[dict[str, Any]]:
        """Most-mentioned resolved entities, with their label mix.

        "Topic" is operationalised as a resolved entity mention. That is a
        transparent definition, unlike a latent topic model that cannot be
        explained to a user reading a chart.
        """
        stmt = (
            select(
                m.Entity.id,
                m.Entity.canonical_name,
                m.Entity.primary_type,
                func.count(m.EntityMention.id).label("mentions"),
            )
            .join(m.EntityMention, m.EntityMention.entity_id == m.Entity.id)
            .where(m.EntityMention.entity_id.is_not(None))
        )
        if date_from is not None:
            stmt = stmt.join(m.Article, m.Article.id == m.EntityMention.article_id).where(
                m.Article.published_at >= _as_dt(date_from)
            )
        stmt = stmt.group_by(m.Entity.id, m.Entity.canonical_name, m.Entity.primary_type)
        stmt = stmt.order_by(func.count(m.EntityMention.id).desc(), m.Entity.canonical_name.asc())
        stmt = stmt.limit(limit)

        out: list[dict[str, Any]] = []
        for entity_id, name, ptype, mentions in self.session.execute(stmt).all():
            label_rows = self.session.execute(
                select(m.SentimentPredictionRow.label, func.count(m.SentimentPredictionRow.id))
                .where(
                    m.SentimentPredictionRow.entity_id == entity_id,
                    m.SentimentPredictionRow.task == "entity_sentiment",
                )
                .group_by(m.SentimentPredictionRow.label)
            ).all()
            sentiment_mix = {label: int(count) for label, count in label_rows}
            out.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": name,
                    "primary_type": ptype,
                    "mentions": int(mentions),
                    "sentiment_mix": sentiment_mix,
                }
            )
        return out

    def ingestion_freshness(self) -> dict[str, Any]:
        """How stale is the corpus, and what happened in the last 24h?

        Operational honesty: a dashboard that never shows its own lag is
        presenting old news as current.
        """
        now = datetime.now()
        latest_fetch = self.session.scalar(select(func.max(m.Article.fetched_at)))
        latest_publish = self.session.scalar(select(func.max(m.Article.published_at)))
        total = int(self.session.scalar(select(func.count(m.Article.id))) or 0)
        last_24h = int(
            self.session.scalar(
                select(func.count(m.Article.id)).where(
                    m.Article.fetched_at >= now - timedelta(hours=24)
                )
            )
            or 0
        )
        publishers = self.session.scalar(
            select(func.count(func.distinct(m.Article.publisher)))
        )
        age_hours: float | None = None
        if isinstance(latest_fetch, datetime):
            age_hours = (now - latest_fetch).total_seconds() / 3600.0
        return {
            "corpus_size": total,
            "articles_last_24h": last_24h,
            "publishers": int(publishers or 0),
            "last_fetched_at": _iso(latest_fetch),
            "last_published_at": _iso(latest_publish),
            "staleness_hours": round(age_hours, 2) if age_hours is not None else None,
            "status": _freshness_status(age_hours),
        }


def _trend_row(row: Sequence[Any]) -> dict[str, Any]:
    period, pos, neg, neu, unc, mean_conf = row
    return {
        "period": str(period),
        "positive": int(pos or 0),
        "negative": int(neg or 0),
        "neutral": int(neu or 0),
        "uncertain": int(unc or 0),
        "mean_score": round(float(mean_conf), 4) if mean_conf is not None else None,
    }


def _freshness_status(age_hours: float | None) -> str:
    if age_hours is None:
        return "empty"
    if age_hours <= 26:
        return "fresh"
    if age_hours <= 72:
        return "stale"
    return "very_stale"


# ==========================================================================
# Watchlists / alerts
# ==========================================================================
class WatchlistRepository:
    """Watchlist CRUD plus the alert dedup path."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, name: str, filters: dict[str, Any] | None = None, **extra: Any
    ) -> dict[str, Any]:
        obj = m.Watchlist(name=name, filters=filters or {}, **extra)
        self.session.add(obj)
        self.session.flush()
        return _watchlist_dict(obj)

    def get(self, watchlist_id: int) -> dict[str, Any] | None:
        obj = self.session.get(m.Watchlist, watchlist_id)
        return _watchlist_dict(obj) if obj else None

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        obj = self.session.scalar(select(m.Watchlist).where(m.Watchlist.name == name))
        return _watchlist_dict(obj) if obj else None

    def list(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(m.Watchlist)
        if active_only:
            stmt = stmt.where(m.Watchlist.is_active.is_(True))
        stmt = stmt.order_by(m.Watchlist.created_at.desc(), m.Watchlist.id.desc())
        return [_watchlist_dict(o) for o in self.session.scalars(stmt).all()]

    def delete(self, watchlist_id: int) -> bool:
        obj = self.session.get(m.Watchlist, watchlist_id)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.flush()
        return True

    def touch_evaluated(self, watchlist_id: int, when: datetime | None = None) -> None:
        obj = self.session.get(m.Watchlist, watchlist_id)
        if obj is not None:
            obj.last_evaluated_at = when or datetime.now()
            self.session.flush()

    # -- alerts ------------------------------------------------------------
    def existing_dedup_keys(self, watchlist_id: int) -> set[str]:
        """All dedup keys already recorded for this watchlist.

        Fetched in one query and compared in Python so a batch evaluation does
        not issue one SELECT per candidate alert.
        """
        rows = self.session.scalars(
            select(m.Alert.dedup_key).where(m.Alert.watchlist_id == watchlist_id)
        ).all()
        return set(rows)

    def create_alert(
        self,
        *,
        watchlist_id: int,
        dedup_key: str,
        event_id: int | None = None,
        article_id: int | None = None,
        threshold: float | None = None,
        score: float | None = None,
        reason: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        """Insert an alert. The UNIQUE constraint on ``dedup_key`` is the real guard.

        ``commit=False`` lets the caller batch inserts; the constraint still
        protects against a race between two concurrent workers.
        """
        obj = m.Alert(
            watchlist_id=watchlist_id,
            event_id=event_id,
            article_id=article_id,
            threshold=threshold,
            score=score,
            reason=reason,
            dedup_key=dedup_key,
        )
        self.session.add(obj)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise
        if commit:
            self.session.commit()
        return _alert_dict(obj)

    def create_alerts_bulk(
        self, watchlist_id: int, candidates: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Insert non-duplicate alerts, returning only those actually created."""
        existing = self.existing_dedup_keys(watchlist_id)
        created: list[dict[str, Any]] = []
        for cand in candidates:
            key = cand["dedup_key"]
            if key in existing:
                continue
            try:
                created.append(
                    self.create_alert(
                        watchlist_id=watchlist_id,
                        dedup_key=key,
                        event_id=cand.get("event_id"),
                        article_id=cand.get("article_id"),
                        threshold=cand.get("threshold"),
                        score=cand.get("score"),
                        reason=cand.get("reason"),
                    )
                )
                existing.add(key)
            except IntegrityError:
                # Lost a race with a concurrent worker; that is a dedup, not an error.
                existing.add(key)
        return created

    def list_alerts(
        self, watchlist_id: int | None = None, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        stmt = select(m.Alert)
        if watchlist_id is not None:
            stmt = stmt.where(m.Alert.watchlist_id == watchlist_id)
        stmt = stmt.order_by(m.Alert.created_at.desc(), m.Alert.id.desc()).limit(limit).offset(offset)
        return [_alert_dict(o) for o in self.session.scalars(stmt).all()]

    def mark_delivered(self, alert_ids: Sequence[int], when: datetime | None = None) -> int:
        if not alert_ids:
            return 0
        when = when or datetime.now()
        count = 0
        for alert_id in alert_ids:
            obj = self.session.get(m.Alert, alert_id)
            if obj is not None:
                obj.delivered_at = when
                count += 1
        self.session.flush()
        return count


def _watchlist_dict(obj: m.Watchlist) -> dict[str, Any]:
    return _row_to_dict(
        obj,
        (
            "id",
            "name",
            "description",
            "filters",
            "owner",
            "is_active",
            "last_evaluated_at",
            "created_at",
            "updated_at",
        ),
    )


def _alert_dict(obj: m.Alert) -> dict[str, Any]:
    return _row_to_dict(
        obj,
        (
            "id",
            "watchlist_id",
            "event_id",
            "article_id",
            "threshold",
            "score",
            "reason",
            "dedup_key",
            "created_at",
            "delivered_at",
        ),
    )


# ==========================================================================
# Models / runs / evaluation
# ==========================================================================
class ModelVersionRepository:
    """Registry rows mirrored into the DB for attribution and the ``/models`` listing."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, *, name: str, version: str, task: str, **extra: Any) -> dict[str, Any]:
        obj = self.session.scalar(
            select(m.ModelVersion).where(
                m.ModelVersion.name == name, m.ModelVersion.version == version
            )
        )
        if obj is None:
            obj = m.ModelVersion(name=name, version=version, task=task, **extra)
            self.session.add(obj)
        else:
            for key, value in extra.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
        self.session.flush()
        return _row_to_dict(
            obj,
            ("id", "name", "version", "task", "framework", "path", "metrics", "trained_at",
             "is_active", "description"),
        )

    def list(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(m.ModelVersion)
        if active_only:
            stmt = stmt.where(m.ModelVersion.is_active.is_(True))
        stmt = stmt.order_by(m.ModelVersion.task.asc(), m.ModelVersion.name.asc())
        return [
            _row_to_dict(
                o,
                ("id", "name", "version", "task", "framework", "path", "metrics", "trained_at",
                 "is_active", "description"),
            )
            for o in self.session.scalars(stmt).all()
        ]

    def active_for_task(self, task: str) -> dict[str, Any] | None:
        obj = self.session.scalar(
            select(m.ModelVersion).where(
                m.ModelVersion.task == task, m.ModelVersion.is_active.is_(True)
            )
        )
        if obj is None:
            return None
        return _row_to_dict(obj, ("id", "name", "version", "task", "framework"))


class RunRepository:
    """Records inference and evaluation runs (provenance + the CI gate's data)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_inference(
        self,
        *,
        run_id: str,
        model_version_id: int | None = None,
        request_hash: str | None = None,
        latency_ms: float | None = None,
        status: str = "complete",
        endpoint: str | None = None,
        stage_provenance: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        obj = m.InferenceRun(
            run_id=run_id,
            model_version_id=model_version_id,
            request_hash=request_hash,
            latency_ms=latency_ms,
            status=status,
            endpoint=endpoint,
            stage_provenance=stage_provenance or [],
            error=error,
        )
        self.session.add(obj)
        self.session.flush()
        return {"id": obj.id, "run_id": obj.run_id, "status": obj.status}

    def latest_evaluations(self, *, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(m.EvaluationRun)
            .order_by(m.EvaluationRun.created_at.desc(), m.EvaluationRun.id.desc())
            .limit(limit)
        )
        return [
            _row_to_dict(
                o,
                ("id", "split", "task", "metrics", "seed", "git_sha", "dataset_hash", "created_at"),
            )
            for o in self.session.scalars(stmt).all()
        ]

    def record_evaluation(
        self, *, split: str, task: str, metrics: dict[str, Any], **extra: Any
    ) -> dict[str, Any]:
        obj = m.EvaluationRun(split=split, task=task, metrics=metrics, **extra)
        self.session.add(obj)
        self.session.flush()
        return {"id": obj.id, "split": obj.split, "task": obj.task}


# --------------------------------------------------------------------------
# Convenience bundle
# --------------------------------------------------------------------------
class Repositories:
    """Namespace bundling every repository for a single session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.articles = ArticleRepository(session)
        self.events = EventRepository(session)
        self.entities = EntityRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.watchlists = WatchlistRepository(session)
        self.models = ModelVersionRepository(session)
        self.runs = RunRepository(session)


__all__ = [
    "AnalyticsRepository",
    "ArticleRepository",
    "EntityRepository",
    "EventRepository",
    "ModelVersionRepository",
    "Repositories",
    "RunRepository",
    "SENTIMENT_LABELS",
    "WatchlistRepository",
]
