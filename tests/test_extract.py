"""Extraction tests: metadata, date handling, normalisation, and honesty rules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from naijafinsent.data.extract import (
    build_article,
    detect_language,
    extract_published_at,
    extract_text,
    extract_title,
)
from naijafinsent.schemas import SourceManifestEntry
from naijafinsent.utils import normalise_text, sha256_text

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"

BUSINESSDAY = SourceManifestEntry(
    source_id="businessday",
    name="BusinessDay",
    base_url="https://businessday.example",
    url_pattern=r"https://businessday\.example/articles/",
    access_method="rss",
    license_note="Fixture only.",
    trust_tier="tier1",
)


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_build_article_from_meta_date_fixture():
    html = read_fixture("article_cbn_mpr.html")
    article = build_article(
        html=html,
        url="https://businessday.example/articles/2026/10/cbn-holds-mpr-27-5",
        source=BUSINESSDAY,
    )

    assert article.title == "CBN holds MPR at 27.5% as inflation eases in September"
    assert article.publisher == "BusinessDay"
    assert article.source_id == "businessday"
    assert article.is_official_release is False
    assert article.published_at == datetime(2026, 10, 8, 6, 30, 0)
    assert article.language == "en"
    assert article.content_hash == sha256_text(article.content)
    assert article.content == normalise_text(article.content)


def test_build_article_from_jsonld_date_fixture():
    html = read_fixture("article_dangote_q3.html")
    article = build_article(
        html=html,
        url="https://businessday.example/articles/2026/10/dangote-cement-q3",
        source=BUSINESSDAY,
    )
    assert article.title == (
        "Dangote Cement reports strong Q3 earnings on higher volumes"
    )
    assert article.published_at == datetime(2026, 10, 9, 9, 5, 0)
    assert "Dangote Cement" in article.content


def test_unknown_date_stays_none():
    html = read_fixture("article_gtco_rights.html")
    article = build_article(
        html=html,
        url="https://businessday.example/articles/2026/10/gtco-rights",
        source=BUSINESSDAY,
    )
    # The fixture has no date metadata: we must NOT invent one.
    assert article.published_at is None
    assert extract_published_at(html) is None
    assert "GTCO" in article.content


def test_content_is_normalised_and_boilerplate_stripped():
    html = read_fixture("article_cbn_mpr.html")
    content = extract_text(html)

    # Nav/footer boilerplate is gone.
    assert "Home" not in content
    assert "Synthetic fixture content" not in content
    # Whitespace is normalised: no runs of spaces or double newlines.
    assert "  " not in content
    assert "\n\n\n" not in content
    # The real article body survives.
    assert "Monetary Policy Rate" in content
    assert "naira" in content.lower()


def test_content_hash_matches_normalised_text():
    html = read_fixture("article_cbn_mpr.html")
    content = extract_text(html)
    assert sha256_text(content) == sha256_text(normalise_text(content))


def test_title_fallback_chain():
    # og:title wins over <title>
    html = b"""
    <html><head>
      <title>Plain Title</title>
      <meta property="og:title" content="OG Title Wins">
    </head><body><h1>H1 Title</h1><p>body</p></body></html>
    """
    assert extract_title(html) == "OG Title Wins"

    # No meta -> <title>
    html2 = b"<html><head><title>Only Title</title></head><body></body></html>"
    assert extract_title(html2) == "Only Title"

    # No title, no h1 -> caller fallback (the URL)
    html3 = b"<html><head></head><body><p>nothing</p></body></html>"
    assert extract_title(html3, fallback="https://x.example/y") == "https://x.example/y"


def test_official_source_sets_flag():
    html = read_fixture("article_cbn_mpr.html")
    cbn = SourceManifestEntry(
        source_id="cbn",
        name="Central Bank of Nigeria",
        base_url="https://www.cbn.example",
        url_pattern=r"https://www\.cbn\.example/",
        access_method="html",
        license_note="Fixture only; official tier.",
        trust_tier="official",
    )
    article = build_article(html=html, url="https://www.cbn.example/press/1", source=cbn)
    assert article.is_official_release is True
    assert article.metadata.get("trust_tier") == "official"


def test_canonical_url_prefers_link_tag():
    html = read_fixture("article_cbn_mpr.html")
    article = build_article(
        html=html,
        url="https://businessday.example/redirected?utm=1",
        source=BUSINESSDAY,
    )
    assert article.canonical_url == (
        "https://businessday.example/articles/2026/10/cbn-holds-mpr-27-5"
    )


def test_bs4_fallback_when_trafilatura_disabled(monkeypatch):
    # Force trafilatura to fail and confirm the BS4 fallback still extracts body.
    import naijafinsent.data.extract as extract_mod

    monkeypatch.setattr(extract_mod, "_extract_with_trafilatura", lambda html: None)
    content = extract_mod.extract_text(read_fixture("article_cbn_mpr.html"))
    assert "Monetary Policy Rate" in content
    assert "Home" not in content


def test_detect_language_heuristic():
    assert detect_language("") == "en"
    assert detect_language("short") == "en"
    english = (
        "The Central Bank of Nigeria said the naira will trade in a narrow band "
        "and that the market has enough liquidity for banks and their customers."
    )
    assert detect_language(english) == "en"

    non_english = " ".join(["zzz", "qqq", "xxx", "yyy", "www"] * 30)
    assert detect_language(non_english) == "und"


def test_unparseable_date_returns_none():
    html = b"""
    <html><head>
      <meta property="article:published_time" content="not a date at all">
    </head><body><p>body</p></body></html>
    """
    assert extract_published_at(html) is None
