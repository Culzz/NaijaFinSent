"""Framework-free corpus storage backed by SQLite (stdlib only).

We chose SQLite over JSONL because it gives us an atomic ``content_hash``
uniqueness constraint (free exact-dedup at write time), indexed lookups, and
WAL-mode concurrent reads — all with zero third-party dependencies. JSONL
*export* is provided for interchange and versioning.

Schema
------
``articles``        one row per article, ``content_hash`` UNIQUE, dedup fields
                    denormalised on the row.
``dedup_relations`` one row per ``(canonical_id, duplicate_id)`` edge, so the
                    clustering is queryable without re-running MinHash/LSH.

The store is intentionally *not* exposed by the API: article text stays internal.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from naijafinsent.schemas import Article

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    article_id        TEXT PRIMARY KEY,
    url               TEXT NOT NULL,
    canonical_url     TEXT,
    title             TEXT NOT NULL,
    publisher         TEXT NOT NULL,
    source_id         TEXT,
    published_at      TEXT,
    fetched_at        TEXT NOT NULL,
    language          TEXT NOT NULL DEFAULT 'en',
    content           TEXT NOT NULL,
    content_hash      TEXT NOT NULL UNIQUE,
    is_official_release INTEGER NOT NULL DEFAULT 0,
    syndicated_from   TEXT,
    is_duplicate      INTEGER NOT NULL DEFAULT 0,
    duplicate_of      TEXT,
    minhash_signature TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);

CREATE TABLE IF NOT EXISTS dedup_relations (
    canonical_id TEXT NOT NULL,
    duplicate_id TEXT NOT NULL,
    similarity   REAL NOT NULL DEFAULT 1.0,
    kind         TEXT NOT NULL DEFAULT 'near',
    PRIMARY KEY (canonical_id, duplicate_id)
);
"""


def _dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _str_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class CorpusStore:
    """SQLite-backed article corpus.

    Parameters
    ----------
    path:
        Database file path. Use ``":memory:"`` (or a ``tmp_path`` file) in
        tests. Parent directories are created automatically.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CorpusStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- serialisation ----------------------------------------------------
    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> Article:
        return Article(
            article_id=row["article_id"],
            url=row["url"],
            canonical_url=row["canonical_url"],
            title=row["title"],
            publisher=row["publisher"],
            source_id=row["source_id"],
            published_at=_str_to_dt(row["published_at"]),
            fetched_at=_str_to_dt(row["fetched_at"]) or _now(),
            language=row["language"],
            content=row["content"],
            content_hash=row["content_hash"],
            is_official_release=bool(row["is_official_release"]),
            syndicated_from=row["syndicated_from"],
            is_duplicate=bool(row["is_duplicate"]),
            duplicate_of=row["duplicate_of"],
            minhash_signature=json.loads(row["minhash_signature"])
            if row["minhash_signature"]
            else None,
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -- writes -----------------------------------------------------------
    def upsert_article(self, article: Article) -> str:
        """Insert or update an article; returns the stored ``article_id``.

        Uniqueness is on ``content_hash``: re-upserting the same content updates
        the existing row rather than creating a second one (idempotency).
        """
        row = self._conn.execute(
            "SELECT article_id FROM articles WHERE content_hash = ?",
            (article.content_hash,),
        ).fetchone()
        stored_id = row["article_id"] if row else article.article_id

        self._conn.execute(
            """
            INSERT INTO articles (
                article_id, url, canonical_url, title, publisher, source_id,
                published_at, fetched_at, language, content, content_hash,
                is_official_release, syndicated_from, is_duplicate, duplicate_of,
                minhash_signature, metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(content_hash) DO UPDATE SET
                url=excluded.url,
                canonical_url=excluded.canonical_url,
                title=excluded.title,
                publisher=excluded.publisher,
                source_id=excluded.source_id,
                published_at=excluded.published_at,
                fetched_at=excluded.fetched_at,
                language=excluded.language,
                content=excluded.content,
                is_official_release=excluded.is_official_release,
                syndicated_from=excluded.syndicated_from,
                is_duplicate=excluded.is_duplicate,
                duplicate_of=excluded.duplicate_of,
                minhash_signature=excluded.minhash_signature,
                metadata=excluded.metadata
            """,
            (
                article.article_id,
                article.url,
                article.canonical_url,
                article.title,
                article.publisher,
                article.source_id,
                _dt_to_str(article.published_at),
                _dt_to_str(article.fetched_at),
                article.language,
                article.content,
                article.content_hash,
                int(article.is_official_release),
                article.syndicated_from,
                int(article.is_duplicate),
                article.duplicate_of,
                json.dumps(article.minhash_signature)
                if article.minhash_signature is not None
                else None,
                json.dumps(article.metadata),
            ),
        )
        self._conn.commit()
        return stored_id

    def mark_duplicates(
        self,
        canonical_id: str,
        duplicate_ids: list[str],
        *,
        similarity: float = 1.0,
        kind: str = "near",
    ) -> int:
        """Record dedup relations and flag the rows. Returns rows touched."""
        touched = 0
        for dup_id in duplicate_ids:
            if dup_id == canonical_id:
                continue
            self._conn.execute(
                """
                INSERT INTO dedup_relations
                    (canonical_id, duplicate_id, similarity, kind)
                VALUES (?,?,?,?)
                ON CONFLICT(canonical_id, duplicate_id) DO UPDATE SET
                    similarity=excluded.similarity,
                    kind=excluded.kind
                """,
                (canonical_id, dup_id, float(similarity), kind),
            )
            cur = self._conn.execute(
                """
                UPDATE articles
                   SET is_duplicate = 1,
                       duplicate_of = ?,
                       syndicated_from = COALESCE(syndicated_from, ?)
                 WHERE article_id = ?
                """,
                (canonical_id, canonical_id, dup_id),
            )
            touched += cur.rowcount
        self._conn.commit()
        return touched

    # -- reads ------------------------------------------------------------
    def get_article(self, article_id: str) -> Article | None:
        row = self._conn.execute(
            "SELECT * FROM articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        return self._row_to_article(row) if row else None

    def get_by_content_hash(self, content_hash: str) -> Article | None:
        row = self._conn.execute(
            "SELECT * FROM articles WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return self._row_to_article(row) if row else None

    def iter_articles(
        self, *, source_id: str | None = None, include_duplicates: bool = True
    ) -> Iterator[Article]:
        """Iterate stored articles, optionally filtered to one source."""
        clauses: list[str] = []
        params: list[Any] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if not include_duplicates:
            clauses.append("is_duplicate = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = self._conn.execute(
            f"SELECT * FROM articles {where} ORDER BY fetched_at, article_id", params
        )
        for row in cur:
            yield self._row_to_article(row)

    def list_relations(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT canonical_id, duplicate_id, similarity, kind FROM dedup_relations"
        )
        return [dict(row) for row in cur]

    def count(self, *, source_id: str | None = None) -> int:
        if source_id is None:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE source_id = ?", (source_id,)
            ).fetchone()
        return int(row["n"])

    def last_fetched_at(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT MAX(fetched_at) AS m FROM articles"
        ).fetchone()
        return _str_to_dt(row["m"]) if row and row["m"] else None

    # -- export -----------------------------------------------------------
    def export_jsonl(self, path: str | Path, *, include_content: bool = False) -> int:
        """Write the corpus to JSONL. Returns the number of rows written.

        By default ``content`` (the full article text) is **omitted** to match
        the publishing policy: exports carry labels/URLs, never article bodies,
        unless explicitly requested for an internal, gitignored artefact.
        """
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with out_path.open("w", encoding="utf-8") as fh:
            for article in self.iter_articles():
                payload = article.model_dump(mode="json")
                if not include_content:
                    payload.pop("content", None)
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                n += 1
        return n


def _now() -> datetime:
    from naijafinsent.utils import utcnow

    return utcnow()
