"""Two-stage deduplication: exact hash match, then near-duplicate clustering.

Stage 1 — **exact**: articles sharing a ``content_hash`` are byte-identical after
normalisation. The later arrival is flagged ``is_duplicate=True`` and its
``duplicate_of`` points at the canonical article.

Stage 2 — **near-duplicate**: a MinHash sketch per article, indexed in an LSH
forest (datasketch). Pairs whose estimated Jaccard similarity is at or above the
threshold (default 0.85) are grouped into clusters. Within a cluster the
**canonical** member is the earliest ``published_at`` (ties broken by
first-seen order); every other member gets ``syndicated_from`` set to the
canonical ``article_id``.

The MinHash signature is stored on the article (``minhash_signature``) so a
corpus can be re-clustered without recomputing sketches.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from naijafinsent.schemas import Article

# Word shingles keep the sketch cheap and robust to line-break noise.
_SHINGLE_SIZE = 5

# datasketch pulls in numpy/scipy and is slow to import, so it is loaded lazily
# by `_datasketch()` the first time a MinHash/LSH object is actually needed.
# Everything below has a pure-Python fallback so the core package imports fast.


def _datasketch() -> Any:
    """Import datasketch on demand, with a clear error if it is missing."""
    try:
        import datasketch  # noqa: PLC0415 - deliberately lazy
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ImportError(
            "MinHash dedup requires datasketch. Install with: pip install datasketch"
        ) from exc
    return datasketch


class _PurePythonMinHash:
    """Minimal MinHash with the datasketch API surface we use.

    Used only if datasketch is unavailable; keeps dedup working (with a small
    speed penalty) rather than failing outright.
    """

    _MERSENNE = (1 << 61) - 1

    def __init__(self, num_perm: int = 128) -> None:
        self.num_perm = num_perm
        self._seeds = [i * 2 + 1 for i in range(num_perm)]
        self.hashvalues = [self._MERSENNE] * num_perm

    def update(self, b: bytes) -> None:
        h = int.from_bytes(hashlib.sha1(b).digest()[:8], "big")
        for i, seed in enumerate(self._seeds):
            v = (h * seed + seed) % self._MERSENNE
            if v < self.hashvalues[i]:
                self.hashvalues[i] = v

    def digest(self) -> list[int]:
        return list(self.hashvalues)

    def jaccard(self, other: "_PurePythonMinHash") -> float:
        same = sum(1 for a, b in zip(self.hashvalues, other.hashvalues) if a == b)
        return same / self.num_perm



def _shingles(text: str, k: int = _SHINGLE_SIZE) -> set[str]:
    """Word-level k-shingles of ``text`` (falls back to whole text if short)."""
    tokens = text.lower().split()
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def compute_minhash(text: str, num_perm: int = 128, k: int = _SHINGLE_SIZE):
    """Build a MinHash sketch over the word k-shingles of ``text``."""
    try:
        ds = _datasketch()
        mh = ds.MinHash(num_perm=num_perm)
    except ImportError:
        mh = _PurePythonMinHash(num_perm=num_perm)
    for shingle in _shingles(text, k):
        mh.update(shingle.encode("utf-8"))
    return mh


def jaccard_from_signature(a: list[int], b: list[int]) -> float:
    """Estimate Jaccard similarity from two equal-length MinHash signatures."""
    if not a or not b or len(a) != len(b):
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a)


@dataclass
class DuplicateCluster:
    """A group of articles judged to be the same story."""

    canonical_id: str
    member_ids: list[str] = field(default_factory=list)
    similarity: float = 1.0
    kind: str = "near"  # "exact" | "near"


class Deduplicator:
    """Incremental exact + near-duplicate detector.

    Call :meth:`add` for each article in insertion order. The method mutates the
    article's dedup fields and returns any clusters newly formed/updated.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.85,
        num_perm: int = 128,
        shingle_size: int = _SHINGLE_SIZE,
    ) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self.shingle_size = shingle_size
        # We compute signature Jaccard ourselves and keep a plain signature
        # store. An LSH index (datasketch) is built lazily only when the corpus
        # grows past a size where a linear scan is wasteful.
        self._lsh = None
        self._lsh_threshold = max(0.1, min(threshold, 0.9))
        self._signatures: dict[str, Any] = {}
        self._by_hash: dict[str, str] = {}  # content_hash -> first article_id
        self._seen_order: list[str] = []
        self._clusters: dict[str, DuplicateCluster] = {}

    def _ensure_lsh(self) -> Any:
        """Build the LSH index on first use, or return None if unavailable."""
        if self._lsh is None and len(self._signatures) >= 200:
            try:
                ds = _datasketch()
                self._lsh = ds.MinHashLSH(
                    threshold=self._lsh_threshold, num_perm=self.num_perm
                )
                for aid, mh in self._signatures.items():
                    self._lsh.insert(aid, mh)
            except Exception:  # noqa: BLE001 - fall back to linear scan
                self._lsh = None
        return self._lsh

    # -- helpers ----------------------------------------------------------
    def _register(self, article: Article) -> Any:
        mh = compute_minhash(article.content, self.num_perm, self.shingle_size)
        article.minhash_signature = [int(v) for v in mh.hashvalues]
        self._signatures[article.article_id] = mh
        if self._lsh is not None:
            self._lsh.insert(article.article_id, mh)
        self._seen_order.append(article.article_id)
        return mh

    def _canonical_for(self, members: list[str], by_id: dict[str, Article]) -> str:
        """Earliest published member wins; ties break on first-seen order."""

        def sort_key(aid: str) -> tuple[int, int]:
            art = by_id[aid]
            published = art.published_at
            # Articles with no date sort last (index 1) so dated ones win.
            if published is None:
                return (1, self._seen_order.index(aid))
            return (0, published.timestamp())

        return min(members, key=lambda aid: (sort_key(aid), self._seen_order.index(aid)))

    def _candidates(self, article_id: str, mh: Any) -> list[str]:
        """Article ids whose signature Jaccard with ``mh`` meets the threshold.

        Uses the LSH index when it is available, otherwise an exact linear scan.
        Either way the *real* threshold is applied here, so results are correct
        regardless of how candidates were generated.
        """
        lsh = self._ensure_lsh()
        if lsh is not None:
            try:
                raw = list(lsh.query(mh))
            except Exception:  # noqa: BLE001 - fall back to scan
                raw = list(self._signatures)
        else:
            raw = list(self._signatures)

        out: list[str] = []
        for cid in raw:
            if cid == article_id:
                continue
            other = self._signatures.get(cid)
            if other is None:
                continue
            if jaccard_from_signature(
                [int(v) for v in mh.hashvalues],
                [int(v) for v in other.hashvalues],
            ) >= self.threshold:
                out.append(cid)
        return out

    # -- public API -------------------------------------------------------
    def add(
        self, article: Article, *, known: dict[str, Article] | None = None
    ) -> DuplicateCluster | None:
        """Add an article; mutate its dedup fields; return a cluster if formed.

        ``known`` maps ``article_id -> Article`` for previously added items and
        is required for canonical selection across a batch. When omitted, only
        the articles seen by this deduplicator are considered.
        """
        by_id = known if known is not None else {}
        by_id.setdefault(article.article_id, article)

        # Stage 1: exact match on content hash.
        prior = self._by_hash.get(article.content_hash)
        if prior is not None and prior != article.article_id:
            article.is_duplicate = True
            article.duplicate_of = prior
            article.syndicated_from = prior
            cluster = self._clusters.setdefault(
                prior, DuplicateCluster(canonical_id=prior, similarity=1.0, kind="exact")
            )
            if article.article_id not in cluster.member_ids:
                cluster.member_ids.append(article.article_id)
            return cluster

        # New content: register the sketch and search for near-duplicates.
        mh = self._register(article)
        self._by_hash.setdefault(article.content_hash, article.article_id)

        neighbours = self._candidates(article.article_id, mh)
        if not neighbours:
            return None

        # Expand each neighbour's own neighbourhood so a whole near-duplicate
        # group collapses into one cluster.
        members: set[str] = {article.article_id, *neighbours}
        for nid in list(neighbours):
            sig = self._signatures.get(nid)
            if sig is None:
                continue
            for other in self._candidates(nid, sig):
                members.add(other)

        member_list = [m for m in self._seen_order if m in members]
        canonical = self._canonical_for(member_list, by_id)

        # Fold any previously existing clusters that overlap this one.
        for member in member_list:
            self._clusters.pop(member, None)

        member_ids = sorted(
            (m for m in member_list if m != canonical),
            key=self._seen_order.index,
        )
        cluster = DuplicateCluster(
            canonical_id=canonical,
            member_ids=member_ids,
            similarity=self._cluster_similarity(canonical, member_ids, by_id),
            kind="near",
        )
        self._clusters[canonical] = cluster

        for member in cluster.member_ids:
            art = by_id.get(member)
            if art is None:
                continue
            # Canonical is the earliest-published copy; the rest are syndicated.
            art.syndicated_from = canonical

        # If a merged cluster promoted a different canonical, drop stale keys.
        canonical_art = by_id.get(canonical)
        for member in cluster.member_ids:
            art = by_id.get(member)
            if art is None or canonical_art is None:
                continue
            if art.content_hash == canonical_art.content_hash:
                art.is_duplicate = True
                art.duplicate_of = canonical
        return cluster

    def _cluster_similarity(
        self, canonical: str, member_ids: list[str], by_id: dict[str, Article]
    ) -> float:
        """Min estimated similarity between the canonical and each member."""
        canonical_art = by_id.get(canonical)
        if canonical_art is None or canonical_art.minhash_signature is None:
            return self.threshold
        sims = []
        for member in member_ids:
            art = by_id.get(member)
            if art is None or art.minhash_signature is None:
                continue
            sims.append(
                jaccard_from_signature(
                    canonical_art.minhash_signature, art.minhash_signature
                )
            )
        return min(sims) if sims else self.threshold

    def add_many(self, articles: list[Article]) -> list[DuplicateCluster]:
        """Add a batch; returns the list of clusters produced."""
        by_id: dict[str, Article] = {a.article_id: a for a in articles}
        clusters: list[DuplicateCluster] = []
        for article in articles:
            cluster = self.add(article, known=by_id)
            if cluster is not None:
                clusters.append(cluster)
        return clusters

    @property
    def clusters(self) -> list[DuplicateCluster]:
        return list(self._clusters.values())


def find_near_duplicates(
    articles: list[Article], threshold: float = 0.85, *, num_perm: int = 128
) -> list[DuplicateCluster]:
    """Convenience wrapper: cluster a whole list and return the clusters.

    Mutates the passed articles' dedup fields (``syndicated_from``,
    ``minhash_signature``, and — for exact matches — ``is_duplicate`` /
    ``duplicate_of``).
    """
    dedup = Deduplicator(threshold=threshold, num_perm=num_perm)
    dedup.add_many(articles)
    return dedup.clusters


def dedup_report(clusters: list[DuplicateCluster]) -> dict:
    """Summarise clustering: counts, pairs, and the threshold interpretation."""
    pairs: list[dict] = []
    total_members = 0
    exact_groups = 0
    near_groups = 0
    for cluster in clusters:
        total_members += len(cluster.member_ids)
        if cluster.kind == "exact":
            exact_groups += 1
        else:
            near_groups += 1
        for member in cluster.member_ids:
            pairs.append(
                {
                    "canonical": cluster.canonical_id,
                    "duplicate": member,
                    "similarity": round(cluster.similarity, 4),
                    "kind": cluster.kind,
                }
            )
    threshold = 1.0
    # Recover a representative threshold from similarity values when possible.
    similarities = [c.similarity for c in clusters if c.kind == "near"]
    if similarities:
        threshold = round(min(similarities), 4)
    return {
        "clusters": len(clusters),
        "exact_clusters": exact_groups,
        "near_clusters": near_groups,
        "duplicate_members": total_members,
        "pairs": pairs,
        "threshold": threshold,
    }
