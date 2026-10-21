"""Article metadata and body extraction.

Primary extractor is **trafilatura** (good boilerplate stripping on news HTML);
the fallback is a small **BeautifulSoup** routine used when trafilatura returns
nothing or raises. Both paths end in the same normalisation, so downstream
hashing and dedup behave identically regardless of which ran.

Honesty rules baked in here:

* We **never invent a date**. If no meta tag / JSON-LD field carries a parseable
  date, ``published_at`` stays ``None``.
* ``language`` is a *cheap heuristic* (see ``detect_language``), not a real
  language ID model — it only distinguishes English from an obvious
  non-English/empty body, and defaults to ``"en"`` for this corpus.
* ``is_official_release`` is derived from the manifest trust tier, not guessed
  from the text.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from naijafinsent.schemas import Article, SourceManifestEntry
from naijafinsent.utils import normalise_text, sha256_text, to_naive_utc, utcnow

# Meta tags (in priority order) that commonly carry the publish date.
_DATE_META_KEYS: tuple[str, ...] = (
    "article:published_time",
    "og:published_time",
    "datePublished",
    "datepublished",
    "pubdate",
    "publishdate",
    "publish-date",
    "publication_date",
    "article.published",
    "sailthru.date",
    "parsely-pub-date",
    "dc.date",
    "dc.date.issued",
    "date",
)

_TITLE_META_KEYS: tuple[str, ...] = (
    "og:title",
    "twitter:title",
)

_CANONICAL_KEYS: tuple[str, ...] = ("og:url",)

# Language heuristic: common English stopwords plus a few Nigerian-finance terms.
_EN_MARKERS: frozenset[str] = frozenset(
    {
        "the", "of", "and", "to", "in", "for", "on", "with", "that", "is",
        "as", "at", "by", "from", "has", "have", "will", "said", "its",
        "naira", "bank", "market", "nigeria", "company", "shares",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = unescape(value).strip()
    return value or None


# --------------------------------------------------------------------------
# Metadata extraction
# --------------------------------------------------------------------------


def _iter_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Yield every JSON-LD object embedded in the page (flattening @graph)."""
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for candidate in data if isinstance(data, list) else [data]:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                objects.extend(item for item in graph if isinstance(item, dict))
            else:
                objects.append(candidate)
    return objects


def _parse_date(value: str | None) -> datetime | None:
    """Parse a date string to a naive-UTC datetime, or ``None`` if unparseable."""
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = date_parser.parse(value, fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        return None
    return to_naive_utc(parsed) if parsed.tzinfo else parsed


def extract_published_at(html: str | bytes) -> datetime | None:
    """Best-effort publish date from meta tags, then JSON-LD. May be ``None``."""
    soup = BeautifulSoup(
        html.decode("utf-8", "replace") if isinstance(html, bytes) else html, "lxml"
    )

    # 1. meta tags
    for key in _DATE_META_KEYS:
        for attr in ("property", "name", "itemprop"):
            tag = soup.find("meta", attrs={attr: key})
            if tag and tag.get("content"):
                parsed = _parse_date(tag["content"])
                if parsed is not None:
                    return parsed

    # 2. <time datetime="...">
    for time_tag in soup.find_all("time"):
        parsed = _parse_date(time_tag.get("datetime") or time_tag.get_text())
        if parsed is not None:
            return parsed

    # 3. JSON-LD
    for obj in _iter_json_ld(soup):
        for field in ("datePublished", "dateCreated", "dateModified"):
            if field in obj:
                parsed = _parse_date(obj.get(field))
                if parsed is not None:
                    return parsed
    return None


def extract_title(html: str | bytes, fallback: str | None = None) -> str:
    """Title fallback chain: og/twitter meta -> <title> -> first <h1> -> fallback."""
    soup = BeautifulSoup(
        html.decode("utf-8", "replace") if isinstance(html, bytes) else html, "lxml"
    )

    for key in _TITLE_META_KEYS:
        for attr in ("property", "name"):
            tag = soup.find("meta", attrs={attr: key})
            if tag and _clean(tag.get("content")):
                return _clean(tag["content"])  # type: ignore[return-value]

    for obj in _iter_json_ld(soup):
        headline = _clean(obj.get("headline"))
        if headline:
            return headline

    if soup.title and _clean(soup.title.get_text()):
        return _clean(soup.title.get_text())  # type: ignore[return-value]

    h1 = soup.find("h1")
    if h1 and _clean(h1.get_text()):
        return _clean(h1.get_text())  # type: ignore[return-value]

    return fallback or ""


def extract_canonical_url(html: str | bytes, url: str) -> str:
    """Canonical URL from <link rel=canonical> or og:url, else the given url."""
    soup = BeautifulSoup(
        html.decode("utf-8", "replace") if isinstance(html, bytes) else html, "lxml"
    )
    link = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    if link and _clean(link.get("href")):
        return _clean(link["href"])  # type: ignore[return-value]
    for key in _CANONICAL_KEYS:
        tag = soup.find("meta", attrs={"property": key})
        if tag and _clean(tag.get("content")):
            return _clean(tag["content"])  # type: ignore[return-value]
    return url


# --------------------------------------------------------------------------
# Body extraction
# --------------------------------------------------------------------------


def _extract_with_trafilatura(html: str) -> str | None:
    """Return trafilatura's plain-text extraction, or ``None`` on failure.

    ``trafilatura`` is imported lazily: it costs ~70s on a cold import on some
    machines (it warms up language-detection data), so it must never sit on the
    package-import path. Callers get the fast BeautifulSoup path until this is
    actually needed.
    """
    try:
        import trafilatura  # noqa: PLC0415 - deliberately lazy, see docstring

        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            output_format="txt",
        )
    except Exception:  # noqa: BLE001 - trafilatura raises assorted errors
        return None
    if result and result.strip():
        return result.strip()
    return None


def _extract_with_bs4(html: str) -> str:
    """Fallback: strip scripts/styles/nav, take the densest article container."""
    soup = BeautifulSoup(html, "lxml")

    for unwanted in soup(
        ["script", "style", "noscript", "nav", "aside", "form", "iframe", "header", "footer"]
    ):
        unwanted.decompose()

    # Prefer a semantic container when the page provides one.
    container = (
        soup.find("article")
        or soup.find(attrs={"itemprop": "articleBody"})
        or soup.find("div", class_=re.compile(r"(article|post|story|content)[-_]?body", re.I))
        or soup.body
        or soup
    )

    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if p)
    if not text.strip():
        text = container.get_text("\n", strip=True)
    return text


def extract_text(html: str | bytes) -> str:
    """Extract the article body text, preferring trafilatura over BS4."""
    html_str = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    text = _extract_with_trafilatura(html_str)
    if text is None:
        text = _extract_with_bs4(html_str)
    return normalise_text(text)


def detect_language(text: str) -> str:
    """Cheap language heuristic for a mostly-English corpus.

    Returns ``"en"`` when the text is empty or looks English; otherwise
    ``"und"`` (undetermined). We deliberately do **not** claim to identify other
    languages — this is a stopword-frequency check, not a classifier, and its
    only downstream role is to flag obviously non-English bodies.
    """
    if not text or len(text) < 20:
        return "en"
    tokens = _WHITESPACE_RE.split(text.lower())[:400]
    if not tokens:
        return "en"
    hits = sum(1 for token in tokens if token.strip(".,;:%()\"'") in _EN_MARKERS)
    return "en" if hits / len(tokens) >= 0.03 else "und"


# --------------------------------------------------------------------------
# Article assembly
# --------------------------------------------------------------------------


def article_id_for(url: str, content_hash: str) -> str:
    """Stable content-addressed-ish id: hash of the URL (kept short and unique)."""
    return sha256_text(url)[:16]


def build_article(
    *,
    html: bytes,
    url: str,
    source: SourceManifestEntry | None = None,
    publisher: str | None = None,
    fetched_at: datetime | None = None,
) -> Article:
    """Assemble an :class:`~naijafinsent.schemas.Article` from raw HTML.

    Parameters
    ----------
    html:
        Raw response body bytes.
    url:
        The URL the bytes came from.
    source:
        Manifest entry; drives ``source_id``, ``publisher``, and
        ``is_official_release`` (official trust tier).
    publisher:
        Overrides the publisher name when no manifest entry is available.
    """
    html_str = html.decode("utf-8", "replace")
    title = extract_title(html_str, fallback=url)
    content = extract_text(html_str)
    content_hash = sha256_text(content)
    published_at = extract_published_at(html_str)
    canonical_url = extract_canonical_url(html_str, url)

    resolved_publisher = publisher or (source.name if source else "unknown")
    is_official = bool(source and source.trust_tier == "official")

    metadata: dict[str, Any] = {}
    if source is not None:
        metadata["trust_tier"] = source.trust_tier

    return Article(
        article_id=article_id_for(url, content_hash),
        url=url,
        canonical_url=canonical_url,
        title=title,
        publisher=resolved_publisher,
        source_id=source.source_id if source else None,
        published_at=published_at,
        fetched_at=fetched_at or utcnow(),
        language=detect_language(content),
        content=content,
        content_hash=content_hash,
        is_official_release=is_official,
        metadata=metadata,
    )
