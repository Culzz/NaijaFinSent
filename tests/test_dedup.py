"""Tests for exact + near-duplicate detection and canonical selection."""

from __future__ import annotations

from datetime import datetime

from naijafinsent.data.dedup import (
    Deduplicator,
    dedup_report,
    find_near_duplicates,
    jaccard_from_signature,
)
from naijafinsent.schemas import Article
from naijafinsent.utils import sha256_text, utcnow

_BASE_BODY = (
    "The Central Bank of Nigeria held the monetary policy rate at 27.5 percent, "
    "citing slower inflation and a firmer naira at the official window. "
    "Banking stocks on the NGX advanced after the decision, led by GTCO and "
    "Zenith Bank, while Dangote Cement and MTN Nigeria also gained."
)


def make_article(
    url: str,
    content: str,
    *,
    published_at: datetime | None = None,
    publisher: str = "Fixture Publisher",
    article_id: str | None = None,
) -> Article:
    """Build a minimal valid Article for dedup tests."""
    return Article(
        article_id=article_id or url.rsplit("/", 1)[-1],
        url=url,
        title="Fixture title",
        publisher=publisher,
        published_at=published_at,
        fetched_at=utcnow(),
        content=content,
        content_hash=sha256_text(content),
    )


def test_exact_duplicates_flagged():
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    b = make_article("https://b.example/2", _BASE_BODY, article_id="b1")
    assert a.content_hash == b.content_hash

    dedup = Deduplicator()
    clusters = dedup.add_many([a, b])

    assert len(clusters) == 1
    assert b.is_duplicate is True
    assert b.duplicate_of == "a1"
    assert b.syndicated_from == "a1"
    assert a.is_duplicate is False


def test_near_duplicates_grouped_above_threshold():
    # Same story, minor edits -> high Jaccard but different hash.
    variant = _BASE_BODY.replace("27.5 percent", "27.5 per cent").replace(
        "advanced", "rallied"
    )
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    b = make_article("https://b.example/2", variant, article_id="b1")
    assert a.content_hash != b.content_hash

    clusters = find_near_duplicates([a, b], threshold=0.85)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert set(cluster.member_ids) == {"b1"}
    assert cluster.canonical_id == "a1"
    assert b.syndicated_from == "a1"
    # Near-dupes are not byte-identical, so is_duplicate stays False.
    assert b.is_duplicate is False


def test_unrelated_articles_not_clustered():
    other = (
        "Nigeria's oil production rose slightly in September according to "
        "OPEC data, with gas supply to power plants improving across the "
        "southern region and export terminals operating normally this month. "
        "Operators reported no major disruptions."
    )
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    b = make_article("https://b.example/2", other, article_id="b1")
    clusters = find_near_duplicates([a, b], threshold=0.85)
    assert clusters == []
    assert b.syndicated_from is None


def test_canonical_is_earliest_published():
    variant = _BASE_BODY.replace("advanced", "rallied")
    # Insert the *later* article first; the earlier one must still win.
    later = make_article(
        "https://b.example/2",
        _BASE_BODY,
        article_id="b1",
        published_at=datetime(2026, 10, 9, 12, 0, 0),
    )
    earlier = make_article(
        "https://a.example/1",
        variant,
        article_id="a1",
        published_at=datetime(2026, 10, 8, 6, 30, 0),
    )
    clusters = find_near_duplicates([later, earlier], threshold=0.85)
    assert len(clusters) == 1
    assert clusters[0].canonical_id == "a1"
    assert later.syndicated_from == "a1"
    assert earlier.syndicated_from is None


def test_canonical_tie_breaks_on_first_seen():
    variant = _BASE_BODY.replace("advanced", "rallied")
    first = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    second = make_article("https://b.example/2", variant, article_id="b1")
    # Neither has a published_at -> first-seen order decides.
    clusters = find_near_duplicates([first, second], threshold=0.85)
    assert len(clusters) == 1
    assert clusters[0].canonical_id == "a1"


def test_minhash_signature_stored():
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    find_near_duplicates([a], threshold=0.85)
    assert a.minhash_signature is not None
    assert len(a.minhash_signature) == 128
    assert all(isinstance(v, int) for v in a.minhash_signature)


def test_jaccard_from_signature_bounds():
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    b = make_article("https://b.example/2", _BASE_BODY, article_id="b1")
    find_near_duplicates([a, b], threshold=0.85)
    assert jaccard_from_signature(a.minhash_signature, a.minhash_signature) == 1.0
    assert jaccard_from_signature([1, 2, 3], [1, 2, 3]) == 1.0
    assert jaccard_from_signature([1, 2, 3], [4, 5, 6]) == 0.0
    assert jaccard_from_signature([], [1, 2]) == 0.0


def test_threshold_is_configurable():
    # A middling-overlap pair clusters at a low threshold but not a high one.
    a_body = _BASE_BODY
    b_body = _BASE_BODY + " " + (
        "Separately, the regulator issued a circular on digital asset service "
        "providers which is unrelated to the rate decision but shares boilerplate."
    )
    a = make_article("https://a.example/1", a_body, article_id="a1")
    b = make_article("https://b.example/2", b_body, article_id="b1")

    low = find_near_duplicates([a, b], threshold=0.5)
    assert len(low) == 1

    a2 = make_article("https://a.example/1", a_body, article_id="a1")
    b2 = make_article("https://b.example/2", b_body, article_id="b1")
    high = find_near_duplicates([a2, b2], threshold=0.99)
    assert high == []


def test_dedup_report_shape():
    variant = _BASE_BODY.replace("advanced", "rallied")
    a = make_article("https://a.example/1", _BASE_BODY, article_id="a1")
    b = make_article("https://b.example/2", variant, article_id="b1")
    clusters = find_near_duplicates([a, b], threshold=0.85)
    report = dedup_report(clusters)

    assert report["clusters"] == 1
    assert report["near_clusters"] == 1
    assert report["exact_clusters"] == 0
    assert report["duplicate_members"] == 1
    assert isinstance(report["pairs"], list)
    assert report["pairs"][0]["canonical"] == "a1"
    assert report["pairs"][0]["duplicate"] == "b1"
    assert 0.0 <= report["threshold"] <= 1.0
