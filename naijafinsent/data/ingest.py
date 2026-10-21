"""Ingestion orchestration: discover -> fetch -> extract -> dedup -> store.

``Ingestor`` is the single entry point for the worker/cron job and for manual
runs. It enforces the Stage 0 audit policy:

* a source with ``enabled: false`` is refused outright;
* a source whose ``robots_checked_at`` is unset (audit **unverified**) is
  refused unless the caller passes ``allow_unverified=True``;
* ``dry_run=True`` performs the full pipeline but writes nothing to the store.

Discovery (index/feed parsing) is delegated to ``sources``; article fetching to
``http.Fetcher``; text extraction to ``extract.build_article``; clustering to
``dedup``; persistence to ``store.CorpusStore``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from naijafinsent.config import Settings, get_settings
from naijafinsent.data import dedup as dedup
from naijafinsent.data import extract as extract
from naijafinsent.data import sources as sources
from naijafinsent.data.http import FetchError, Fetcher
from naijafinsent.data.store import CorpusStore
from naijafinsent.schemas import Article, SourceManifestEntry
from naijafinsent.utils import utcnow


class SourceNotAllowedError(Exception):
    """Raised when a source is disabled or its audit is unverified."""


@dataclass
class SourceReport:
    """Per-source outcome, included in the overall :class:`IngestReport`."""

    source_id: str
    discovered: int = 0
    fetched: int = 0
    extracted: int = 0
    stored: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "discovered": self.discovered,
            "fetched": self.fetched,
            "extracted": self.extracted,
            "stored": self.stored,
            "duplicates": self.duplicates,
            "errors": list(self.errors),
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class IngestReport:
    """Structured result of an ingestion run."""

    started_at: datetime
    finished_at: datetime | None = None
    dry_run: bool = False
    sources: list[SourceReport] = field(default_factory=list)
    dedup_summary: dict | None = None

    @property
    def total_stored(self) -> int:
        return sum(s.stored for s in self.sources)

    @property
    def total_duplicates(self) -> int:
        return sum(s.duplicates for s in self.sources)

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "dry_run": self.dry_run,
            "total_stored": self.total_stored,
            "total_duplicates": self.total_duplicates,
            "sources": [s.as_dict() for s in self.sources],
            "dedup_summary": self.dedup_summary,
        }


class Ingestor:
    """Orchestrates a crawl of one or more audited sources."""

    def __init__(
        self,
        *,
        store: CorpusStore | None = None,
        fetcher: Fetcher | None = None,
        settings: Settings | None = None,
        manifest_path=None,
        dedup_threshold: float = 0.85,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or CorpusStore(self.settings.data_dir / "corpus.db")
        self.fetcher = fetcher or Fetcher(settings=self.settings)
        self.manifest_path = manifest_path
        self.dedup_threshold = dedup_threshold

    # -- audit enforcement ------------------------------------------------
    def _check_allowed(
        self, source: SourceManifestEntry, *, allow_unverified: bool
    ) -> None:
        if not source.enabled:
            raise SourceNotAllowedError(
                f"source {source.source_id!r} is disabled in the manifest"
            )
        if source.robots_checked_at is None and not allow_unverified:
            raise SourceNotAllowedError(
                f"source {source.source_id!r} audit is unverified "
                f"(robots_checked_at is null); pass allow_unverified=True to override"
            )

    # -- discovery --------------------------------------------------------
    def discover(self, source: SourceManifestEntry) -> list[str]:
        """Fetch the source's index document and return candidate article URLs."""
        index_url = self._index_url(source)
        result = self.fetcher.fetch(index_url)
        urls = sources.discover_links(source, result.content, base_url=index_url)
        # Apply the manifest's URL pattern to prune feed noise.
        return sources.filter_by_pattern(urls, source.url_pattern)

    @staticmethod
    def _index_url(source: SourceManifestEntry) -> str:
        """Where to look for the list of articles.

        The manifest stores only a base URL; the index path is derived from the
        access method. These are the conventional paths and are validated during
        the Stage 0 audit.
        """
        base = source.base_url.rstrip("/")
        if source.access_method == "rss":
            return f"{base}/feed/"
        if source.access_method == "sitemap":
            return f"{base}/sitemap.xml"
        return base

    # -- the pipeline -----------------------------------------------------
    def ingest_source(
        self,
        source_id: str,
        *,
        limit: int | None = None,
        dry_run: bool = False,
        allow_unverified: bool = False,
    ) -> SourceReport:
        """Run the full pipeline for one source."""
        source = sources.get_source(source_id, self.manifest_path)
        report = SourceReport(source_id=source_id)

        try:
            self._check_allowed(source, allow_unverified=allow_unverified)
        except SourceNotAllowedError as exc:
            report.skipped_reason = str(exc)
            return report

        try:
            candidate_urls = self.discover(source)
        except FetchError as exc:
            report.errors.append(f"discovery failed: {exc}")
            return report
        except Exception as exc:  # noqa: BLE001 - report, don't crash the run
            report.errors.append(f"discovery error: {exc!r}")
            return report

        if limit is not None:
            candidate_urls = candidate_urls[:limit]
        report.discovered = len(candidate_urls)

        articles: list[Article] = []
        for url in candidate_urls:
            try:
                result = self.fetcher.fetch(url)
                report.fetched += 1
            except FetchError as exc:
                report.errors.append(f"fetch {url}: {exc}")
                continue
            try:
                article = extract.build_article(
                    html=result.content, url=url, source=source
                )
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"extract {url}: {exc!r}")
                continue
            articles.append(article)
            report.extracted += 1

        # Dedup across the batch *and* against what is already stored.
        known: dict[str, Article] = {a.article_id: a for a in self.store.iter_articles()}
        known.update({a.article_id: a for a in articles})
        dedup_instance = dedup.Deduplicator(threshold=self.dedup_threshold)
        clusters = []
        for article in articles:
            cluster = dedup_instance.add(article, known=known)
            if cluster is not None:
                clusters.append(cluster)
        report.duplicates = sum(len(c.member_ids) for c in clusters)

        if dry_run:
            report.skipped_reason = "dry_run: no writes performed"
            return report

        for article in articles:
            self.store.upsert_article(article)
            report.stored += 1

        for cluster in clusters:
            self.store.mark_duplicates(
                cluster.canonical_id,
                cluster.member_ids,
                similarity=cluster.similarity,
                kind=cluster.kind,
            )

        return report

    def ingest_all(
        self,
        *,
        limit: int | None = None,
        dry_run: bool = False,
        allow_unverified: bool = False,
        source_ids: list[str] | None = None,
    ) -> IngestReport:
        """Run the pipeline for every (or a subset of) manifest source."""
        report = IngestReport(started_at=utcnow(), dry_run=dry_run)
        manifests = sources.load_manifests(self.manifest_path)
        if source_ids is not None:
            wanted = set(source_ids)
            manifests = [m for m in manifests if m.source_id in wanted]

        all_clusters: list = []
        for manifest in manifests:
            source_report = self.ingest_source(
                manifest.source_id,
                limit=limit,
                dry_run=dry_run,
                allow_unverified=allow_unverified,
            )
            report.sources.append(source_report)

        if not dry_run:
            relations = self.store.list_relations()
            all_clusters = [
                dedup.DuplicateCluster(
                    canonical_id=r["canonical_id"],
                    member_ids=[r["duplicate_id"]],
                    similarity=r["similarity"],
                    kind=r["kind"],
                )
                for r in relations
            ]
        report.dedup_summary = dedup.dedup_report(all_clusters)
        report.finished_at = utcnow()
        return report
