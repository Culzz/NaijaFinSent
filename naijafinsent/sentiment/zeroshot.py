"""FinBERT zero-shot sentiment -- an off-the-shelf comparison point.

``ProsusAI/finbert`` ships with its own 3-way head (positive/negative/neutral)
trained on English financial news (Reuters/Financial PhraseBank). We use that
head *as-is* and map its labels onto our 4-way space:

* positive -> positive, negative -> negative, neutral -> neutral
* our ``uncertain`` class is never produced by FinBERT; when its neutral
  confidence is low and the top-2 gap is small we flag the text as *uncertain*
  by splitting mass -- see :meth:`predict_proba`.

This model is **not** trained on Nigerian data. It is a baseline to be beaten,
and it always reports ``calibrated=False`` plus an explicit limitation note that
callers must surface in the UI.
"""

from __future__ import annotations

from typing import Sequence

from naijafinsent.schemas import EvidenceSpan
from naijafinsent.sentiment.base import LABELS, BaseSentimentModel

__all__ = ["FinBertZeroShotSentiment", "FINBERT_NAME", "LIMITATION_NOTE"]

FINBERT_NAME = "ProsusAI/finbert"

LIMITATION_NOTE = (
    "FinBERT is trained on English financial news (Reuters/Financial PhraseBank), "
    "NOT on Nigerian data. It does not model naira/FX, CBN policy, or NGX-specific "
    "language, and it has no 'uncertain' class. Treat outputs as an uncalibrated, "
    "out-of-domain baseline."
)

#: FinBERT's native label strings -> our label space.
_LABEL_MAP: dict[str, str] = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
}

# Threshold on (top1 - top2) below which neutral output is re-labelled uncertain.
_UNCERTAIN_GAP = 0.15


def _require_transformers():
    try:
        import torch  # noqa: F401
        from transformers import pipeline  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "FinBertZeroShotSentiment requires torch + transformers. "
            "Install with: pip install 'naijafinsent[ml]'."
        ) from exc
    import torch
    from transformers import pipeline

    return torch, pipeline


class FinBertZeroShotSentiment(BaseSentimentModel):
    """FinBERT's own sentiment head, mapped to the NaijaFinSent label space."""

    name = "finbert-zeroshot"
    version = "0.1.0"
    # Honest: FinBERT's softmax is not calibrated on our data.
    calibrated = False

    def __init__(
        self,
        *,
        model_name: str = FINBERT_NAME,
        device: int = -1,
        uncertain_gap: float = _UNCERTAIN_GAP,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.uncertain_gap = uncertain_gap
        self.labels = LABELS
        self._pipe = None
        self.limitations: list[str] = [LIMITATION_NOTE]

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        _torch, pipeline = _require_transformers()
        # top_k=None returns all class scores.
        self._pipe = pipeline(
            "text-classification",
            model=self.model_name,
            top_k=None,
            device=self.device,
            truncation=True,
            max_length=512,
        )

    def _raw_scores(self, text: str) -> dict[str, float]:
        """FinBERT label -> score, restricted to its native 3 classes."""
        self._ensure_loaded()
        result = self._pipe(text)
        # pipeline with top_k=None returns [ [ {label,score}, ... ] ].
        items = result[0] if result and isinstance(result[0], list) else result
        scores: dict[str, float] = {}
        for item in items or []:
            native = str(item["label"]).lower()
            mapped = _LABEL_MAP.get(native, native)
            scores[mapped] = scores.get(mapped, 0.0) + float(item["score"])
        return scores

    def predict_proba(self, text: str) -> dict[str, float]:
        scores = self._raw_scores(text)
        dist = {lab: 0.0 for lab in self.labels}
        for lab, p in scores.items():
            if lab in dist:
                dist[lab] = p

        # Re-allocate low-confidence neutral mass to 'uncertain' so our 4-way
        # space is respected. This is a documented heuristic, not a learned
        # mapping.
        ranked = sorted(dist.items(), key=lambda kv: kv[1], reverse=True)
        if ranked and ranked[0][0] == "neutral" and len(ranked) > 1:
            gap = ranked[0][1] - ranked[1][1]
            if gap < self.uncertain_gap:
                shift = dist["neutral"] * 0.5
                dist["neutral"] -= shift
                dist["uncertain"] += shift

        total = sum(dist.values())
        if total <= 0:
            return {lab: 1.0 / len(self.labels) for lab in self.labels}
        return {lab: v / total for lab, v in dist.items()}

    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        """FinBERT gives no native attribution; return the first sentence(s)."""
        return self._fallback_evidence(text, max_spans=max(1, k))

    def predict_batch(self, texts: Sequence[str]):
        return [self.predict(t) for t in texts]
