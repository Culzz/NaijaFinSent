"""Ingestion adapter: bridge the core ingestor to the database.

The core package owns fetching, parsing and dedup. This adapter owns the
*persistence* side: turning core records into rows, assigning an
``ingest_run_id``, and recording an ``article_versions`` entry whenever a URL we
have already stored comes back with a different hash.

Failure policy
--------------
The core ingestor may not be present (another agent owns it) and the network may
be unreachable in CI. Both are normal, so:

* a missing core module is reported via ``skipped_reason`` and returns an empty
  result, it does not raise;
* per-source failures are counted and reported, and one bad source never aborts
  the run;
* the run still writes whatever it did fetch.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from naijafinsent.config import Settings, get_settings
from naijafinsent.utils import sha256_text, slugify, utcnow
from sqlalchemy.orm import Session

from services.api.app.db import models as m
from services.api.app.db.repositories import ArticleRepository
from services.worker.ids import new_run_id

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """What one ingestion run actually did. Reported, not inferred."""

    ingest_run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    fetched: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    versions_recorded: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ingest_run_id": self.ingest_run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "fetched": self.fetched,
            "created": self.created,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "versions_recorded": self.versions_recorded,
            "errors": self.errors,
            "skipped_reason": self.skipped_reason,
        }


def _coerce_source_id(publisher: str | None, source_id: str | None) -> str | None:
    if source_id:
        return source_id
    return slugify(publisher) if publisher else None


def _record_from_core(item: Any) -> dict[str, Any]:
    """Normalise a core ingestor record into the dict this adapter consumes.

    Accepts either a pydantic ``Article`` from ``naijafinsent.schemas`` or a plain
    mapping, because the core ingestor's exact return type is still settling and
    coupling to one shape would break the worker for no benefit.
    """
    if isinstance(item, dict):
        get = item.get
        content = get("content")
        title = get("title") or ""
    else:  # pydantic model or simple namespace
        content = getattr(item, "content", None)
        title = getattr(item, "title", "") or ""

    def _val(key: str, default: Any = None) -> Any:
        return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

    return {
        "url": _val("url"),
        "canonical_url": _val("canonical_url"),
        "title": title,
        "publisher": _val("publisher") or "",
        "source_id": _val("source_id"),
        "published_at": _val("published_at"),
        "language": _val("language") or "en",
        "content": content,
        "content_hash": _val("content_hash") or (sha256_text(content) if content else None),
        "is_official_release": bool(_val("is_official_release", False)),
        "is_duplicate": bool(_val("is_duplicate", False)),
    }


def persist_articles(
    session: Session,
    items: Iterable[Any],
    *,
    ingest_run_id: str,
    settings: Settings | None = None,
    retain_content: bool = False,
    result: IngestResult | None = None,
) -> IngestResult:
    """Write core ingestor records into ``articles`` (+ ``article_versions``).

    ``retain_content`` defaults to **False** to match the legal data policy: we
    store labels, hashes and URLs unless the source's licence permits retention.
    Even when True, only rows whose source allows it should be passed in.

    Not committed here: the caller decides the transaction boundary, which keeps
    a partial failure atomic.
    """
    settings = settings or get_settings()
    result = result or IngestResult(ingest_run_id=ingest_run_id, started_at=utcnow())
    repo = ArticleRepository(session)

    for raw in items:
        result.fetched += 1
        try:
            record = _record_from_core(raw)
        except Exception as exc:  # noqa: BLE001 - one malformed record is not a run failure
            result.errors.append(f"unparseable record: {exc!r}")
            continue

        url = record.get("url")
        if not url:
            result.errors.append("record without a url was skipped")
            continue
        content_hash = record.get("content_hash") or ""
        if not content_hash:
            result.errors.append(f"record without a content_hash was skipped: {url}")
            continue

        existing = repo.get_by_url(url)
        body = record["content"] if retain_content else None

        if existing is None:
            try:
                repo.create(
                    url=url,
                    title=record["title"] or url,
                    publisher=record["publisher"] or "unknown",
                    content_hash=content_hash,
                    published_at=record["published_at"],
                    canonical_url=record["canonical_url"],
                    source_id=_coerce_source_id(record["publisher"], record["source_id"]),
                    language=record["language"],
                    content=body,
                    is_official_release=record["is_official_release"],
                    ingest_run_id=ingest_run_id,
                    word_count=len(body.split()) if body else None,
                    is_duplicate=record["is_duplicate"],
                )
                result.created += 1
                _add_version(
                    session,
                    article_id=_article_id_by_url(session, url),
                    content_hash=content_hash,
                    change_type="first_seen",
                    word_count=len(body.split()) if body else None,
                )
                result.versions_recorded += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"insert failed for {url}: {exc!r}")
            continue

        # Already stored. Same hash => nothing changed; new hash => a live edit.
        if existing["content_hash"] == content_hash:
            result.duplicates += 1
            continue

        try:
            repo.update(
                existing["id"],
                content_hash=content_hash,
                title=record["title"] or existing["title"],
                ingest_run_id=ingest_run_id,
                fetched_at=utcnow(),
                **({"content": body} if retain_content else {}),
            )
            _add_version(
                session,
                article_id=existing["id"],
                content_hash=content_hash,
                change_type="body_changed",
                word_count=len(body.split()) if body else None,
                diff_summary=f"content hash changed from {existing['content_hash'][:12]} "
                f"to {content_hash[:12]}",
            )
            result.versions_recorded += 1
            result.updated += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"update failed for {url}: {exc!r}")

    result.finished_at = utcnow()
    return result


def _add_version(
    session: Session,
    *,
    article_id: int | None,
    content_hash: str,
    change_type: str,
    word_count: int | None = None,
    diff_summary: str | None = None,
) -> None:
    """Record a version row, tolerating the duplicate that a retry can produce."""
    if article_id is None:
        return
    exists = (
        session.query(m.ArticleVersion)
        .filter(
            m.ArticleVersion.article_id == article_id,
            m.ArticleVersion.content_hash == content_hash,
        )
        .first()
    )
    if exists is not None:
        return
    session.add(
        m.ArticleVersion(
            article_id=article_id,
            content_hash=content_hash,
            change_type=change_type,
            word_count=word_count,
            diff_summary=diff_summary,
        )
    )


def _article_id_by_url(session: Session, url: str) -> int | None:
    row = session.query(m.Article.id).filter(m.Article.url == url).first()
    return int(row[0]) if row else None


# --------------------------------------------------------------------------
# Core ingestor bridge
# --------------------------------------------------------------------------
def core_ingest_callable() -> Any | None:
    """Return the core ingestion entry point if the module exists.

    Imported defensively because ``naijafinsent.data.ingest`` is owned by another
    workstream and may not have landed yet. Absence means "skip", not "crash".
    """
    for module_path, attr in (
        ("naijafinsent.data.ingest", "ingest_all"),
        ("naijafinsent.data.ingest", "run_ingest"),
        ("naijafinsent.data.ingest", "fetch_articles"),
    ):
        try:
            module = __import__(module_path, fromlist=[attr])
        except Exception:  # noqa: BLE001
            continue
        fn = getattr(module, attr, None)
        if callable(fn):
            return fn
    return None


def run_ingestion(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
    sources: list[str] | None = None,
    ingest_run_id: str | None = None,
    items: Iterable[Any] | None = None,
) -> IngestResult:
    """Run one ingestion pass and persist the result.

    ``items`` lets a caller (the worker's test, an operator replaying a fixture)
    inject records directly and skip the network entirely.
    """
    settings = settings or get_settings()
    run_id = ingest_run_id or new_run_id("ingest")
    result = IngestResult(ingest_run_id=run_id, started_at=utcnow())

    if items is None:
        fn = core_ingest_callable()
        if fn is None:
            result.skipped_reason = (
                "core ingestion module (naijafinsent.data.ingest) is not available; "
                "nothing was fetched"
            )
            result.finished_at = utcnow()
            logger.info("ingestion skipped: %s", result.skipped_reason)
            return result
        try:
            kwargs: dict[str, Any] = {}
            if limit is not None:
                kwargs["limit"] = limit
            if sources is not None:
                kwargs["sources"] = sources
            items = _iter_records(fn(**kwargs) if kwargs else fn())
        except Exception as exc:  # noqa: BLE001 - network/parse failure is expected
            result.errors.append(f"core ingestion raised: {exc!r}")
            result.finished_at = utcnow()
            logger.warning("ingestion failed: %r", exc)
            return result

    persist_articles(
        session,
        items,
        ingest_run_id=run_id,
        settings=settings,
        result=result,
    )
    result.finished_at = utcnow()
    logger.info(
        "ingestion %s: fetched=%d created=%d updated=%d duplicates=%d errors=%d",
        run_id,
        result.fetched,
        result.created,
        result.updated,
        result.duplicates,
        len(result.errors),
    )
    return result


def _iter_records(returned: Any) -> Iterator[Any]:  # noqa: ANN401
    """Yield records from whatever the core ingestor returned.

    Copes with a list, an iterator, or a dict keyed by source name.
    """
    if returned is None:
        return
    if isinstance(returned, dict):
        for value in returned.values():
            yield from _iter_records(value)
        return
    if isinstance(returned, str | bytes):
        return
    try:
        yield from returned
    except TypeError:
        yield returned


__all__ = [
    "IngestResult",
    "core_ingest_callable",
    "persist_articles",
    "run_ingestion",
]
