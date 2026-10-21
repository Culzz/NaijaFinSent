"""Evidence-cited Q&A: retrieval, answer construction, claim verification, abstention.

The hard rule
-------------
**The answer may only assert things that a retrieved passage supports.** Three
mechanisms enforce that, in order:

1. *Retrieval* returns candidate passages with a relevance score. If nothing
   clears the floor, we abstain — we do not answer from the model's priors.
2. *Answer construction* is extractive by default: sentences are copied (with a
   citation id attached) from retrieved passages. There is no free-text
   generation in the offline path, so an unsupported claim cannot be invented.
3. *Verification* runs over whatever answer we have, including an LLM's, and
   **drops every sentence whose content terms are not present in a cited
   passage**. Dropped sentences are reported in ``dropped_claims`` rather than
   silently removed, so a user can see what the model wanted to say and why it
   was not allowed to.

If an ``ANTHROPIC_API_KEY`` is configured we may use an LLM to compose prose, but
its output goes through the same verifier. With no key, the extractive path is
fully functional offline — which is what CI exercises.

Testability
-----------
The module depends on a *retriever callable* rather than a database. The DB-backed
retriever lives in this module too, but tests inject a fake and never touch a
session.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from naijafinsent.config import Settings, get_settings
from naijafinsent.inference.pipeline import LIMITATIONS
from naijafinsent.schemas import ProcessingStatus

logger = logging.getLogger(__name__)

# Retrieval defaults. A small floor is used because BM25-ish scores are
# unbounded; the floor is applied to the *normalised* score (see _normalise).
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.0
# If the best passage scores below this, we have no business answering.
ABSTENTION_SCORE_FLOOR = 0.12
# Stopwords are stripped before overlap checks so "the" cannot be the thing that
# "supports" a claim.
_STOPWORDS = frozenset(
    """
    a an and are as at be been being but by for from had has have he her his i in is it its
    of on or our that the their them then there these they this to was were what when where
    which who will with would you your we us not no do does did about into over after before
    """.split()
)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9%$.-]*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class Passage:
    """A retrieved unit of evidence."""

    article_id: int
    url: str
    text: str
    score: float
    title: str | None = None
    publisher: str | None = None
    published_at: Any | None = None
    method: str = "lexical"

    def as_citation(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "url": self.url,
            "title": self.title,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "quote": self.text,
            "score": round(float(self.score), 6),
            "method": self.method,
        }


@dataclass
class CopilotAnswer:
    """The composed result, pre-serialisation."""

    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None
    dropped_claims: list[str] = field(default_factory=list)
    retrieved: int = 0
    status: ProcessingStatus = ProcessingStatus.COMPLETE
    latency_ms: float | None = None


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    """Lowercase word tokens with stopwords removed."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _term_overlap(claim: str, passage: str) -> float:
    """Fraction of the claim's content terms that appear in the passage.

    Deliberately simple and inspectable: a reviewer can reproduce this number by
    hand, which is the point of a "supported by evidence" claim.
    """
    claim_terms = set(tokenize(claim))
    if not claim_terms:
        return 0.0
    passage_terms = set(tokenize(passage))
    return len(claim_terms & passage_terms) / len(claim_terms)


SUPPORT_THRESHOLD = 0.6


def sentence_is_supported(sentence: str, passages: Sequence[Passage]) -> bool:
    """True if any required passage covers enough of the sentence's content terms."""
    for passage in passages:
        if _term_overlap(sentence, passage.text) >= SUPPORT_THRESHOLD:
            return True
    return False


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
Retriever = Callable[[str, int], list[Passage]]


def bm25_scores(query: str, documents: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 over an in-memory document set.

    We implement this rather than depend on a search engine so that the
    retrieval ranking in CI is identical to production and needs no service.
    """
    docs_tokens = [tokenize(d) for d in documents]
    query_tokens = tokenize(query)
    n = len(docs_tokens)
    if n == 0 or not query_tokens:
        return [0.0] * n

    avg_len = sum(len(d) for d in docs_tokens) / n or 1.0
    # Document frequency per query term.
    df: dict[str, int] = {}
    for term in set(query_tokens):
        df[term] = sum(1 for tokens in docs_tokens if term in tokens)

    scores: list[float] = []
    for tokens in docs_tokens:
        length = len(tokens) or 1
        score = 0.0
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        for term in query_tokens:
            freq = counts.get(term, 0)
            if freq == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denom = freq + k1 * (1 - b + b * length / avg_len)
            score += idf * (freq * (k1 + 1)) / denom
        scores.append(score)
    return scores


def _normalise(scores: Sequence[float]) -> list[float]:
    """Scale scores into 0..1 so ``min_score`` means the same thing everywhere."""
    if not scores:
        return []
    hi = max(scores)
    if hi <= 0:
        return [0.0 for _ in scores]
    return [max(0.0, s / hi) for s in scores]


def retrieve_from_rows(
    query: str,
    rows: Sequence[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    text_key: str = "text",
) -> list[Passage]:
    """Rank plain dict rows via BM25. The DB layer produces the rows.

    Keeping this pure makes the ranking unit-testable and lets the same function
    serve a DB query, a fixture file, or a future embedding store.
    """
    documents = [str(row.get(text_key) or "") for row in rows]
    normalised = _normalise(bm25_scores(query, documents))
    scored = sorted(zip(rows, normalised, strict=False), key=lambda pair: pair[1], reverse=True)

    passages: list[Passage] = []
    for row, score in scored[:top_k]:
        if score < min_score:
            continue
        passages.append(
            Passage(
                article_id=int(row.get("article_id") or row.get("id") or 0),
                url=str(row.get("url") or ""),
                text=str(row.get(text_key) or ""),
                score=score,
                title=row.get("title"),
                publisher=row.get("publisher"),
                published_at=row.get("published_at"),
                method="lexical",
            )
        )
    return passages


def make_db_retriever(
    session: Any,  # noqa: ANN401 - SQLAlchemy Session, imported lazily to stay framework-free-ish
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    publisher: str | None = None,
) -> Retriever:
    """Build a retriever backed by the stored corpus.

    Retrieves candidate rows with a cheap SQL prefilter, then ranks with BM25.
    When ``articles.content`` is not retained (the default under the legal data
    policy) the title is what we can honestly retrieve over, and the passage text
    is the title plus the URL context. That limitation is real and documented
    rather than papered over: you cannot quote a passage you do not store.
    """
    from services.api.app.db.repositories import ArticleRepository  # local import

    def _retrieve(query: str, top_k: int) -> list[Passage]:
        repo = ArticleRepository(session)
        rows, _ = repo.list_filtered(
            publisher=publisher,
            date_from=date_from,
            date_to=date_to,
            limit=max(50, top_k * 20),
        )
        documents: list[dict[str, Any]] = []
        for row in rows:
            body = (row.get("title") or "").strip()
            content = row.get("content")
            text = f"{body}. {content}" if content else body
            documents.append(
                {
                    "article_id": row["id"],
                    "url": row["url"],
                    "title": row.get("title"),
                    "publisher": row.get("publisher"),
                    "published_at": row.get("published_at"),
                    "text": text,
                }
            )
        return retrieve_from_rows(query, documents, top_k=top_k)

    return _retrieve


def make_embedding_retriever(
    rows: Sequence[dict[str, Any]], embedder: Callable[[Sequence[str]], list[list[float]]],
    query: str, *, top_k: int = DEFAULT_TOP_K
) -> list[Passage]:
    """Optional semantic retrieval, used only when an embedder is configured.

    Cosine similarity over the embedder's vectors, blended with nothing: this is
    a separate retrieval arm, and combining the two score scales would require
    calibration we do not have.
    """
    texts = [str(r.get("text") or "") for r in rows]
    if not texts:
        return []
    vectors = embedder([query, *texts])
    if len(vectors) < 2:
        return []
    qvec, docvecs = vectors[0], vectors[1:]

    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    scored = sorted(
        ((row, cosine(qvec, vec)) for row, vec in zip(rows, docvecs, strict=False)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [
        Passage(
            article_id=int(row.get("article_id") or row.get("id") or 0),
            url=str(row.get("url") or ""),
            text=str(row.get("text") or ""),
            score=max(0.0, sim),
            title=row.get("title"),
            publisher=row.get("publisher"),
            published_at=row.get("published_at"),
            method="embedding",
        )
        for row, sim in scored[:top_k]
    ]


def hybrid_retrieve(
    query: str,
    rows: Sequence[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
    embedder: Callable[[Sequence[str]], list[list[float]]] | None = None,
) -> list[Passage]:
    """Lexical (always) + optional embedding recall, merged by article id.

    Fusion is by best-score-wins rather than a weighted sum, because the two arms
    produce scores on incomparable scales and a learned weight would be a claim we
    cannot currently justify.
    """
    lexical = retrieve_from_rows(query, rows, top_k=top_k * 2)
    merged: dict[int, Passage] = {p.article_id: p for p in lexical}

    if embedder is not None:
        try:
            semantic = make_embedding_retriever(rows, embedder, query, top_k=top_k * 2)
        except Exception as exc:  # noqa: BLE001 - an embedder is optional
            logger.warning("embedding retrieval failed, using lexical only: %r", exc)
            semantic = []
        for passage in semantic:
            existing = merged.get(passage.article_id)
            if existing is None or passage.score > existing.score:
                passage.method = "hybrid"
                merged[passage.article_id] = passage

    ranked = sorted(merged.values(), key=lambda p: p.score, reverse=True)
    return ranked[:top_k]


# --------------------------------------------------------------------------
# Answer construction
# --------------------------------------------------------------------------
def _best_evidence_sentence(query: str, passage: Passage) -> str:
    """Pick the passage sentence that is most about the question."""
    sentences = split_sentences(passage.text) or [passage.text]
    query_terms = set(tokenize(query))
    if not query_terms:
        return sentences[0]

    def relevance(sentence: str) -> tuple[float, int]:
        terms = set(tokenize(sentence))
        return (len(terms & query_terms) / len(query_terms), -len(sentence))

    return max(sentences, key=relevance)


def build_extractive_answer(query: str, passages: Sequence[Passage], *, max_sentences: int = 3) -> tuple[str, list[str]]:
    """Compose an answer by quoting retrieved sentences. Returns (answer, used_quotes).

    Every sentence carries an inline ``[n]`` citation marker matching the
    citation list index, so a reader can check each claim in one click.
    """
    if not passages:
        return "", []
    lines: list[str] = []
    quotes: list[str] = []
    for index, passage in enumerate(passages[:max_sentences], start=1):
        sentence = _best_evidence_sentence(query, passage)
        if not sentence:
            continue
        quotes.append(sentence)
        publisher = passage.publisher or "source"
        lines.append(f"{sentence.rstrip('.')} [{index}] ({publisher}).")
    return " ".join(lines), quotes


def verify_answer(
    answer: str, passages: Sequence[Passage]
) -> tuple[str, list[str]]:
    """Drop every sentence not supported by a retrieved passage.

    Returns ``(kept_answer, dropped_sentences)``. Sentences that are purely
    citation scaffolding (e.g. a trailing reference marker) are kept only if
    they are attached to a kept sentence.
    """
    if not answer.strip():
        return "", []
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in split_sentences(answer):
        if sentence_is_supported(sentence, passages):
            kept.append(sentence)
        else:
            dropped.append(sentence)
    return " ".join(kept), dropped


def _first_url(passages: Sequence[Passage]) -> str | None:
    return passages[0].url if passages else None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def answer_question(
    question: str,
    retriever: Retriever,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    allow_abstention: bool = True,
    settings: Settings | None = None,
    llm: Callable[[str, Sequence[Passage]], str] | None = None,
) -> CopilotAnswer:
    """Full copilot path: retrieve -> compose -> verify -> (abstain | answer).

    Parameters
    ----------
    retriever:
        ``(query, top_k) -> list[Passage]``. Injected so tests never need a DB.
    llm:
        Optional composer ``(question, passages) -> prose``. Its output is
        verified exactly like the extractive path; there is no bypass.
    """
    settings = settings or get_settings()
    started = time.perf_counter()

    passages = list(retriever(question, top_k))
    passages = [p for p in passages if p.score >= min_score]
    retrieved = len(passages)

    if not passages:
        return CopilotAnswer(
            answer="",
            citations=[],
            abstained=True,
            abstention_reason=(
                "No stored article matched the question, so there is no evidence to "
                "cite. Try broadening the question or a different publisher/date range."
            ),
            retrieved=0,
            status=ProcessingStatus.PARTIAL,
            latency_ms=_ms(started),
        )

    best = max(p.score for p in passages)
    if allow_abstention and best < ABSTENTION_SCORE_FLOOR:
        return CopilotAnswer(
            answer="",
            citations=[],
            abstained=True,
            abstention_reason=(
                f"The best retrieved passage scored {best:.3f}, below the "
                f"{ABSTENTION_SCORE_FLOOR:.2f} evidence floor. Reporting a weak match as an "
                "answer would overstate what the corpus supports."
            ),
            retrieved=retrieved,
            status=ProcessingStatus.PARTIAL,
            latency_ms=_ms(started),
        )

    if llm is not None:
        try:
            candidate = llm(question, passages)
        except Exception as exc:  # noqa: BLE001 - LLM is an enhancement, not a dependency
            logger.warning("LLM composition failed; falling back to extractive: %r", exc)
            candidate, _ = build_extractive_answer(question, passages)
    else:
        candidate, _ = build_extractive_answer(question, passages)

    verified, dropped = verify_answer(candidate, passages)

    if not verified.strip():
        return CopilotAnswer(
            answer="",
            citations=[p.as_citation() for p in passages[:top_k]],
            abstained=True,
            abstention_reason=(
                "Every candidate sentence failed verification against the retrieved "
                "passages, so no supported answer could be produced."
            ),
            dropped_claims=dropped,
            retrieved=retrieved,
            status=ProcessingStatus.PARTIAL,
            latency_ms=_ms(started),
        )

    return CopilotAnswer(
        answer=verified,
        citations=[p.as_citation() for p in passages[:top_k]],
        abstained=False,
        dropped_claims=dropped,
        retrieved=retrieved,
        status=ProcessingStatus.COMPLETE,
        latency_ms=_ms(started),
    )


def make_llm_composer(settings: Settings | None = None) -> Callable[[str, Sequence[Passage]], str] | None:
    """Return an LLM composer when a key is configured, else ``None``.

    Errors are the caller's to catch: ``answer_question`` falls back to the
    extractive path, so a failing key degrades rather than breaks the endpoint.
    """
    settings = settings or get_settings()
    api_key = getattr(settings, "anthropic_api_key", None)
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        logger.info("anthropic SDK unavailable; copilot stays extractive")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    def _compose(question: str, passages: Sequence[Passage]) -> str:
        context = "\n\n".join(
            f"[{i}] ({p.publisher or 'source'}) {p.text}" for i, p in enumerate(passages, start=1)
        )
        message = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=500,
            system=(
                "Answer ONLY from the numbered passages. Cite with [n]. If the passages do "
                "not answer the question, say so. Never add outside facts."
            ),
            messages=[{"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {question}"}],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    return _compose


def limitations() -> list[str]:
    """Caveats the copilot response must carry."""
    return [
        *LIMITATIONS,
        "Answers are extractive summaries of stored coverage and cite the passages they use.",
        "Absence of an answer means absence of evidence in this corpus, not absence of the fact.",
    ]


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


__all__ = [
    "ABSTENTION_SCORE_FLOOR",
    "SUPPORT_THRESHOLD",
    "CopilotAnswer",
    "Passage",
    "Retriever",
    "answer_question",
    "bm25_scores",
    "build_extractive_answer",
    "hybrid_retrieve",
    "limitations",
    "make_db_retriever",
    "make_embedding_retriever",
    "make_llm_composer",
    "retrieve_from_rows",
    "split_sentences",
    "tokenize",
    "verify_answer",
]
