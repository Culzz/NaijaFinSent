"""Deterministic lexicon sentiment model.

This is the demo/offline sentiment model: transparent word-list polarity with
negation handling and an uncertain bias for hedging language. It exists so the
API, worker, frontend, and the CI golden gate all run with **zero trained
weights** on more machines. It is not a research-grade model — the TF-IDF and
transformer families are — and its model card entry says exactly that.
"""
from __future__ import annotations

import re

from naijafinsent.constants import SENTIMENT_LABELS
from naijafinsent.schemas import EvidenceSpan
from naijafinsent.sentiment.base import BaseSentimentModel

# Hand-curated polarity seeds, Nigerian financial-news register.
POSITIVE = {
    "record profit", "rises", "rose", "jumped", "surged", "gains", "growth",
    "profitable", "profitability", "return to profit", "returned to profit", "strong",
    "upbeat", "boost", "boosts", "production increase", "improve", "improved",
    "stabilise", "stabilizes", "appreciates", "appreciation", "upgrade",
    "approved dividend", "record revenue", "exceeds", "beats", "recovery",
    "repairs", "expansion", "highest", "best", "restored", "profit surge",
}
NEGATIVE = {
    "loss", "losses", "falls", "fell", "drops", "dropped", "slump", "slumped",
    "depreciation", "record low", "weak", "weakens", "disappointed",
    "disappointment", "undermining", "crisis", "warning", "warnings", "fine",
    "fined", "penalty", "sanction", "sacked", "cut", "cuts", "revoke",
    "revoked", "suspended", "crackdown", "shortage", "theft", "vandal",
    "vandalism", "scarcity", "decline", "recession", "downgrade", "default",
    "distress", "fraud", "probe", "investigation",
}
HEDGES = {
    "expect", "expected", "expects", "forecast", "forecasts", "unclear",
    "uncertain", "remain", "remains", "awaiting", "waiting", " analysts",
    "may", "might", "could", "rumour", "rumored", "planned",
}
NEGATORS = {"not", "no", "never", "without", "hardly", "barely", "don't", "doesn't", "did not", "didnt"}

_TOKEN = re.compile(r"[a-z']+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


class LexiconSentimentModel(BaseSentimentModel):
    """Transparent lexicon baseline over the four-label space."""

    name = "naija-lexicon-sentiment"
    version = "0.1.0"
    calibrated = False
    labels = SENTIMENT_LABELS

    def __init__(self, *, positive: set[str] | None = None, negative: set[str] | None = None):
        self.positive = {p.lower() for p in (positive or POSITIVE)}
        self.negative = {n.lower() for n in (negative or NEGATIVE)}
        self.hedges = HEDGES
        self.negators = NEGATORS

    # -- internals -------------------------------------------------------
    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        return _TOKEN.findall(lowered)

    def _count(self, text: str, vocab: set[str]) -> tuple[int, list[str]]:
        lowered = f" {text.lower()} "
        hits = [term for term in vocab if f" {term} " in lowered or term in lowered.split()]
        return len(hits), hits

    # -- BaseSentimentModel implementation --------------------------------
    def predict_proba(self, text: str) -> dict[str, float]:
        tokens = self._tokens(text)
        n = max(len(tokens), 1)
        pos_n, pos_hits = self._count(text, self.positive)
        neg_n, neg_hits = self._count(text, self.negative)
        hedge_n, _ = self._count(text, self.hedges)

        # Negation flips the polarity of a nearby hit ("no losses", "not weak").
        if any(tok in self.negators for tok in tokens):
            pos_n, neg_n = neg_n, pos_n

        # Appearance-weighted, normalised to probabilities that sum to 1.
        pos = pos_n / n
        neg = neg_n / n
        hed = min(1.0, hedge_n / max(n, 1)) / 2
        neutral = 0.5
        uncertain = 0.15 + hed

        # Pull neutral/uncertain up and dump remaining mass onto sentiment side.
        signal = pos + neg
        if signal == 0:
            probs = {"positive": 0.12, "negative": 0.12, "neutral": 0.5, "uncertain": 0.26}
            return probs
        raw = {
            "positive": pos + neutral * 0.25,
            "negative": neg + neutral * 0.25,
            "neutral": neutral * 0.12,
            "uncertain": 0.05 + hed,
        }
        # Signal dominates: scale the winner up, others down, then renormalise.
        winner = max(raw, key=raw.get)
        for key in raw:
            raw[key] = raw[key] * (2.2 if key == winner else 0.7)
        total = sum(raw.values())
        return {k: round(v / total, 4) for k, v in raw.items()}

    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        lowered = text.lower()
        vocab = (
            self.positive
            if (self._count(text, self.positive)[0] >= self._count(text, self.negative)[0])
            else self.negative
        )
        sentences = _SENT_SPLIT.split(text.strip())
        cursor = 0
        scored: list[tuple[int, EvidenceSpan]] = []
        for sent in sentences:
            start = text.find(sent, cursor)
            if start < 0:
                continue
            cursor = start + len(sent)
            hits = sum(1 for term in vocab if term in sent.lower())
            scored.append((hits, EvidenceSpan(text=sent, start=start, end=start + len(sent))))
        scored.sort(key=lambda t: -t[0])
        picked = [span for hits, span in scored[:k] if hits > 0]
        if picked:
            return picked
        # No polarity hit: point at the first sentence so a reviewer has context.
        if sentences:
            span = EvidenceSpan(text=sentences[0], start=0, end=len(sentences[0]))
            return [span]
        return [EvidenceSpan(text=text, start=0, end=len(text))] if text else []


__all__ = ["LexiconSentimentModel"]
