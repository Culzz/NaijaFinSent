"""Source manifests and link discovery.

Discovery is deliberately separated from fetching: this module parses feeds,
sitemaps, and HTML indexes into *candidate article URLs* only. It never fetches
an article body — that is ``ingest.py``'s job via ``http.Fetcher`` and
``extract.py``.

Supported discovery routes:

* **RSS / Atom** — read ``<item><link>`` (RSS) and ``<entry><link href>`` (Atom).
* **Sitemaps** — read ``<loc>`` entries, including sitemap-index recursion.
* **HTML index** — scan ``<a href>`` and keep URLs matching a regex pattern.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from lxml import etree

from naijafinsent.config import get_settings
from naijafinsent.schemas import SourceManifestEntry

_MANIFEST_FILENAME = "sources.json"

# Strip an XML namespace so we can match localnames regardless of prefix.
_NS_RE = re.compile(r"\{[^}]*\}")


class ManifestError(Exception):
    """The manifest file is missing, malformed, or fails schema validation."""


def default_manifest_path() -> Path:
    """Where the shipped manifest lives (``<data_dir>/manifests/sources.json``)."""
    return get_settings().data_dir / "manifests" / _MANIFEST_FILENAME


def load_manifests(path: Path | str | None = None) -> list[SourceManifestEntry]:
    """Load and validate every source entry from the manifest file.

    Accepts either the wrapped form ``{"version", "generated_at", "sources"}``
    or a bare list of entries. Raises ``ManifestError`` on any problem so a
    broken manifest cannot silently produce an empty crawl list.
    """
    manifest_path = Path(path) if path is not None else default_manifest_path()
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc

    if isinstance(raw, dict):
        entries = raw.get("sources")
    else:
        entries = raw
    if not isinstance(entries, list):
        raise ManifestError("manifest has no 'sources' list")

    manifests: list[SourceManifestEntry] = []
    for i, entry in enumerate(entries):
        try:
            manifests.append(SourceManifestEntry.model_validate(entry))
        except Exception as exc:  # pydantic ValidationError, plus any shape error
            raise ManifestError(f"source[{i}] invalid: {exc}") from exc
    return manifests


def load_manifest_file(path: Path | str | None = None) -> dict:
    """Return the whole manifest document (for version/metadata inspection)."""
    manifest_path = Path(path) if path is not None else default_manifest_path()
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def get_source(source_id: str, path: Path | str | None = None) -> SourceManifestEntry:
    """Return the manifest entry for ``source_id`` or raise ``KeyError``."""
    for entry in load_manifests(path):
        if entry.source_id == source_id:
            return entry
    raise KeyError(f"unknown source_id: {source_id!r}")


# --------------------------------------------------------------------------
# Discovery — RSS / Atom
# --------------------------------------------------------------------------


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag).lower()


def discover_from_rss(xml_bytes: bytes, base_url: str = "") -> list[str]:
    """Extract candidate article URLs from an RSS 2.0 or Atom document."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        # Some feeds advertise non-UTF-8; retry after a lenient parse.
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser=parser)
        if root is None:
            return []

    urls: list[str] = []
    seen: set[str] = set()

    def add(link: str | None) -> None:
        if not link:
            return
        link = link.strip()
        if not link:
            return
        if base_url:
            link = urljoin(base_url, link)
        if link not in seen:
            seen.add(link)
            urls.append(link)

    for el in root.iter():
        name = _localname(el.tag)
        if name == "link":
            # Atom: <link href="..."/> ; RSS: <link>https://...</link>
            href = el.get("href")
            if href:
                add(href)
            elif el.text:
                add(el.text)
        elif name == "guid" and el.get("ispermalink", "true").lower() == "true":
            if el.text:
                add(el.text)
    return urls


# --------------------------------------------------------------------------
# Discovery — sitemaps
# --------------------------------------------------------------------------


def discover_from_sitemap(
    xml_bytes: bytes, base_url: str = "", *, include_sitemaps: bool = True
) -> list[str]:
    """Extract ``<loc>`` URLs from a sitemap or sitemap index."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser=parser)
        if root is None:
            return []

    root_name = _localname(root.tag)
    is_index = root_name == "sitemapindex"

    urls: list[str] = []
    seen: set[str] = set()
    for el in root.iter():
        if _localname(el.tag) != "loc" or not el.text:
            continue
        loc = el.text.strip()
        if base_url:
            loc = urljoin(base_url, loc)
        if is_index and not include_sitemaps:
            # Caller only wants article URLs, not nested sitemap URLs.
            continue
        if loc not in seen:
            seen.add(loc)
            urls.append(loc)
    return urls


def is_sitemap_index(xml_bytes: bytes) -> bool:
    """True when the document is a ``<sitemapindex>`` (points at sub-sitemaps)."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser=parser)
        if root is None:
            return False
    return _localname(root.tag) == "sitemapindex"


# --------------------------------------------------------------------------
# Discovery — generic HTML anchors
# --------------------------------------------------------------------------


def discover_from_html(
    html: str | bytes,
    base_url: str,
    url_pattern: str | None = None,
    *,
    max_links: int = 500,
) -> list[str]:
    """Scan a paginated HTML index for anchors matching ``url_pattern``.

    ``url_pattern`` is a regex matched against the absolute URL. When omitted,
    every http(s) anchor on the page is returned (deduped, capped).
    """
    if isinstance(html, bytes):
        soup = BeautifulSoup(html, "lxml")
    else:
        soup = BeautifulSoup(html, "lxml")

    pattern = re.compile(url_pattern) if url_pattern else None
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if pattern is not None and not pattern.search(absolute):
            continue
        # Drop fragments so the same page isn't queued twice.
        absolute = absolute.split("#", 1)[0]
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)
            if len(urls) >= max_links:
                break
    return urls


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------


def discover_links(
    manifest: SourceManifestEntry,
    document: str | bytes,
    *,
    base_url: str | None = None,
) -> list[str]:
    """Discover candidate URLs from a fetched index document.

    Chooses the parser from the document's shape rather than trusting the
    manifest alone: an XML document is routed to the RSS or sitemap parser, and
    everything else is treated as HTML.
    """
    base = base_url or manifest.base_url
    raw = document.encode("utf-8") if isinstance(document, str) else document
    head = raw.lstrip()[:256].lower()

    if head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head:
        if b"<feed" in head and b"<rss" not in head:
            return discover_from_rss(raw, base_url=base)
        return discover_from_rss(raw, base_url=base)
    if b"<urlset" in head or b"<sitemapindex" in head:
        return discover_from_sitemap(raw, base_url=base)
    # Fall back to HTML scanning with the manifest's URL pattern.
    return discover_from_html(document, base, manifest.url_pattern)


def filter_by_pattern(urls: list[str], url_pattern: str) -> list[str]:
    """Keep only URLs matching ``url_pattern`` (used to prune feed noise)."""
    pattern = re.compile(url_pattern)
    return [u for u in urls if pattern.search(u)]


def _parse_checked_at(value: str | None) -> datetime | None:
    """Helper for callers building manifests: parse an ISO timestamp or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
