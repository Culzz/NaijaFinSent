"""CorpusStore tests: upsert, idempotency, dedup relations, and export."""

from __future__ import annotations

import json
from datetime import datetime

from naijafinsent.data.store import CorpusStore
from naijafinsent.schemas import Article
from naijafinsent.utils import sha256_text, utcnow


def make_article(
    url: str,
    content: str,
    *,
    article_id: str | None = None,
    source_id: str = "businessday",
    publisher: str = "BusinessDay",
    published_at: datetime | None = None,
) -> Article:
    return Article(
        article_id=article_id or url.rsplit("/", 1)[-1],
        url=url,
        title="Fixture title",
        publisher=publisher,
        source_id=source_id,
        published_at=published_at,
        fetched_at=utcnow(),
        content=content,
        content_hash=sha256_text(content),
        minhash_signature=[1, 2, 3],
        metadata={"trust_tier": "tier1"},
    )


def test_upsert_and_get(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        article = make_article("https://a.example/1", "CBN holds the MPR steady.", article_id="a1")
        stored_id = store.upsert_article(article)
        assert stored_id == "a1"
        assert store.count() == 1

        fetched = store.get_article("a1")
        assert fetched is not None
        assert fetched.content_hash == article.content_hash
        assert fetched.minhash_signature == [1, 2, 3]
        assert fetched.metadata["trust_tier"] == "tier1"
    finally:
        store.close()


def test_upsert_is_idempotent_on_content_hash(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        first = make_article("https://a.example/1", "Same story text.", article_id="a1")
        second = make_article("https://b.example/2", "Same story text.", article_id="b1")
        assert first.content_hash == second.content_hash

        store.upsert_article(first)
        store.upsert_article(second)
        # Only one row: content_hash is UNIQUE and upsert updates in place.
        assert store.count() == 1

        # The URL is updated to the latest upsert, but the id is stable.
        by_hash = store.get_by_content_hash(first.content_hash)
        assert by_hash is not None
        assert by_hash.url == "https://b.example/2"
    finally:
        store.close()


def test_upsert_updates_fields_in_place(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        article = make_article("https://a.example/1", "Text v1.", article_id="a1")
        store.upsert_article(article)

        # Same content hash, richer metadata (e.g. dedup discovered later).
        article.title = "Updated title"
        article.is_duplicate = True
        article.duplicate_of = "canonical-1"
        store.upsert_article(article)

        assert store.count() == 1
        fetched = store.get_article("a1")
        assert fetched is not None
        assert fetched.title == "Updated title"
        assert fetched.is_duplicate is True
        assert fetched.duplicate_of == "canonical-1"
    finally:
        store.close()


def test_iter_articles_and_filters(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        store.upsert_article(
            make_article("https://a.example/1", "Body one.", article_id="a1", source_id="businessday")
        )
        store.upsert_article(
            make_article("https://b.example/2", "Body two.", article_id="b1", source_id="nairametrics")
        )
        store.upsert_article(
            make_article("https://c.example/3", "Body three.", article_id="c1", source_id="businessday")
        )

        assert store.count() == 3
        assert store.count(source_id="businessday") == 2
        assert store.count(source_id="nairametrics") == 1

        ids = {a.article_id for a in store.iter_articles(source_id="businessday")}
        assert ids == {"a1", "c1"}

        all_ids = {a.article_id for a in store.iter_articles()}
        assert all_ids == {"a1", "b1", "c1"}
    finally:
        store.close()


def test_mark_duplicates_records_relation(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        canonical = make_article("https://a.example/1", "Canonical story.", article_id="a1")
        dup = make_article("https://b.example/2", "Different copy of the story.", article_id="b1")
        store.upsert_article(canonical)
        store.upsert_article(dup)

        touched = store.mark_duplicates("a1", ["b1"], similarity=0.91, kind="near")
        assert touched == 1

        relations = store.list_relations()
        assert len(relations) == 1
        assert relations[0]["canonical_id"] == "a1"
        assert relations[0]["duplicate_id"] == "b1"
        assert relations[0]["kind"] == "near"

        flagged = store.get_article("b1")
        assert flagged is not None
        assert flagged.is_duplicate is True
        assert flagged.syndicated_from == "a1"

        # iter_articles(include_duplicates=False) drops the flagged row.
        non_dupes = {a.article_id for a in store.iter_articles(include_duplicates=False)}
        assert non_dupes == {"a1"}
    finally:
        store.close()


def test_export_jsonl_omits_content_by_default(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        store.upsert_article(
            make_article(
                "https://a.example/1",
                "CBN held the MPR.",
                article_id="a1",
                published_at=datetime(2026, 10, 8, 6, 30, 0),
            )
        )
        store.upsert_article(make_article("https://b.example/2", "Naira firmed.", article_id="b1"))

        out = tmp_path / "export.jsonl"
        n = store.export_jsonl(out)
        assert n == 2

        lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2
        # Policy: exports never carry article text unless asked.
        assert all("content" not in row for row in lines)
        assert {row["article_id"] for row in lines} == {"a1", "b1"}
        # Content hash and URL are preserved for reproducibility.
        assert all("content_hash" in row and "url" in row for row in lines)
    finally:
        store.close()


def test_export_jsonl_with_content_when_explicit(tmp_path):
    store = CorpusStore(tmp_path / "corpus.db")
    try:
        store.upsert_article(make_article("https://a.example/1", "CBN held the MPR.", article_id="a1"))
        out = tmp_path / "full.jsonl"
        store.export_jsonl(out, include_content=True)
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert row["content"] == "CBN held the MPR."
    finally:
        store.close()


def test_persists_across_reopen(tmp_path):
    db = tmp_path / "corpus.db"
    store = CorpusStore(db)
    store.upsert_article(make_article("https://a.example/1", "Persist me.", article_id="a1"))
    store.close()

    reopened = CorpusStore(db)
    try:
        assert reopened.count() == 1
        assert reopened.get_article("a1") is not None
    finally:
        reopened.close()
