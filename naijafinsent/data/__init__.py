"""Data engine: fetch, discover, extract, dedup, and store.

Public surface
--------------
``Fetcher``/``is_safe_url``      polite, SSRF-guarded HTTP
``load_manifests``/``get_source`` source registry + link discovery
``build_article``                 HTML -> :class:`~naijafinsent.schemas.Article`
``Deduplicator``/``find_near_duplicates``  exact + near-duplicate clustering
``CorpusStore``                   SQLite-backed corpus (internal only)
``Ingestor``                      end-to-end orchestration

This package is framework-free and never imports the API database layer.
"""

from __future__ import annotations

from naijafinsent.data.dedup import (
    Deduplicator,
    DuplicateCluster,
    dedup_report,
    find_near_duplicates,
    jaccard_from_signature,
)
from naijafinsent.data.extract import (
    build_article,
    detect_language,
    extract_published_at,
    extract_text,
    extract_title,
)
from naijafinsent.data.http import (
    ALLOWED_CONTENT_TYPES,
    FetchError,
    Fetcher,
    FetchResult,
    HostRateLimiter,
    SSRFBlockedError,
    TooLargeError,
    UnsupportedContentTypeError,
    is_safe_url,
)
from naijafinsent.data.ingest import (
    Ingestor,
    IngestReport,
    SourceNotAllowedError,
    SourceReport,
)
from naijafinsent.data.sources import (
    ManifestError,
    discover_from_html,
    discover_from_rss,
    discover_from_sitemap,
    discover_links,
    filter_by_pattern,
    get_source,
    load_manifests,
)
from naijafinsent.data.store import CorpusStore

__all__ = [
    # http
    "ALLOWED_CONTENT_TYPES",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "HostRateLimiter",
    "SSRFBlockedError",
    "TooLargeError",
    "UnsupportedContentTypeError",
    "is_safe_url",
    # sources
    "ManifestError",
    "discover_from_html",
    "discover_from_rss",
    "discover_from_sitemap",
    "discover_links",
    "filter_by_pattern",
    "get_source",
    "load_manifests",
    # extract
    "build_article",
    "detect_language",
    "extract_published_at",
    "extract_text",
    "extract_title",
    # dedup
    "Deduplicator",
    "DuplicateCluster",
    "dedup_report",
    "find_near_duplicates",
    "jaccard_from_signature",
    # store
    "CorpusStore",
    # ingest
    "Ingestor",
    "IngestReport",
    "SourceNotAllowedError",
    "SourceReport",
]
