"""Shared interface for every sentiment model.

Concrete models (TF-IDF, transformer, zero-shot) subclass
:class:`BaseSentimentModel` so the inference pipeline can treat them
interchangeably. Two invariants matter here:

* Every prediction carries ``evidence`` -- the span(s) of source text that most
  support the predicted class. Different model families derive this differently;
  :meth:`BaseSentimentModel.explain` documents the method honestly per family.
* Every prediction carries a :class:`~naijafinsent.schemas.ModelRef` with the
  model's ``name``/``version``/``task``/``calibrated`` so the API can display
  provenance and the honesty caveats that go with it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from naijafinsent.constants import SENTIMENT_LABELS, TASK_SENTIMENT
from naijafinsent.preprocessing.text import split_sentences
from naijafinsent.schemas import EvidenceSpan, ModelRef, SentimentLabel, SentimentPrediction

__all__ = ["BaseSentimentModel", "LABELS"]


#: Canonical label space, sourced from constants (never re-typed here).
LABELS: tuple[str, ...] = SENTIMENT_LABELS


def _to_label(value: str | SentimentLabel) -> SentimentLabel:
    """Coerce a string/enum to ``SentimentLabel`` (raises on unknown values)."""
    if isinstance(value, SentimentLabel):
        return value
    return SentimentLabel(str(value))


class BaseSentimentModel(ABC):
    """Abstract base implementing the pipeline ``SentimentModel`` protocol.

    Subclasses must set ``name``, ``version``, ``calibrated`` and implement
    :meth:`predict_proba` and :meth:`explain`. ``predict_batch`` and ``predict``
    are provided here in terms of those primitives.
    """

    #: Human-readable model identifier, e.g. ``"tfidf-logreg"``.
    name: str = "base-sentiment"
    version: str = "0.0.0"
    #: Always ``"sentiment"`` for this hierarchy.
    task: str = TASK_SENTIMENT
    #: True only when probabilities were calibrated (temperature/Platt) on
    #: held-out data. Be honest: default is False.
    calibrated: bool = False
    #: The label space this model emits.
    labels: tuple[str, ...] = LABELS

    # -- required primitives -------------------------------------------
    @abstractmethod
    def predict_proba(self, text: str) -> dict[str, float]:
        """Return a probability distribution over :attr:`labels` for ``text``.

        Implementations must return a dict whose keys are exactly
        :attr:`labels` and whose values are non-negative and sum to ~1.0.
        """

    @abstractmethod
    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        """Return evidence spans supporting ``label`` for ``text``.

        Document the derivation per family; see module docstring. Must return a
        non-empty list when ``text`` is non-empty (fall back to the first
        sentence(s) if no span-specific signal is available).
        """

    # -- optional overridable training / persistence -------------------
    def fit(self, texts: Sequence[str], labels: Sequence[str], **kwargs) -> BaseSentimentModel:
        """Train the model. Base default refuses rather than silently no-ops."""
        raise NotImplementedError(
            f"{type(self).__name__} does not implement fit(); it is a pre-trained model."
        )

    def save(self, path) -> None:  # noqa: ANN001 - path type varies by family
        raise NotImplementedError(f"{type(self).__name__} does not implement save()")

    @classmethod
    def load(cls, path) -> BaseSentimentModel:  # noqa: ANN001
        raise NotImplementedError(f"{cls.__name__} does not implement load()")

    # -- derived API ----------------------------------------------------
    def model_ref(self) -> ModelRef:
        return ModelRef(
            name=self.name,
            version=self.version,
            task=self.task,
            calibrated=self.calibrated,
        )

    def _build_prediction(
        self,
        label: str | SentimentLabel,
        probs: dict[str, float],
        evidence: list[EvidenceSpan],
    ) -> SentimentPrediction:
        """Assemble a validated ``SentimentPrediction``."""
        lab = _to_label(label)
        # Guarantee evidence is present for non-empty text.
        clean_probs = {k: float(v) for k, v in probs.items()}
        conf = clean_probs.get(lab.value)
        if conf is None:
            conf = max(clean_probs.values()) if clean_probs else 0.0
        return SentimentPrediction(
            label=lab,
            confidence=_clip01(conf),
            probabilities={k: _clip01(v) for k, v in clean_probs.items()},
            evidence=evidence,
            model=self.model_ref(),
        )

    def _fallback_evidence(self, text: str, max_spans: int = 2) -> list[EvidenceSpan]:
        """First sentence(s) of ``text`` as evidence, with exact offsets.

        Honest, model-agnostic fallback: we do not claim these are causal; they
        are the sentence(s) a human should read first.
        """
        if not text:
            return []
        spans: list[EvidenceSpan] = []
        cursor = 0
        for sent in split_sentences(text)[:max_spans]:
            idx = text.find(sent, cursor)
            if idx < 0:
                idx = text.find(sent)
            if idx < 0:
                continue
            spans.append(EvidenceSpan(text=sent, start=idx, end=idx + len(sent)))
            cursor = idx + len(sent)
        if not spans:
            spans.append(EvidenceSpan(text=text, start=0, end=len(text)))
        return spans

    def predict(self, text: str) -> SentimentPrediction:
        """Classify ``text`` and return a fully-populated prediction."""
        probs = self.predict_proba(text)
        label = max(probs.items(), key=lambda kv: kv[1])[0] if probs else LABELS[0]
        evidence = self.explain(text, label)
        if not evidence:
            evidence = self._fallback_evidence(text)
        return self._build_prediction(label, probs, evidence)

    def predict_batch(self, texts: Sequence[str]) -> list[SentimentPrediction]:
        """Classify many texts (naive loop; subclasses may override to vectorise)."""
        return [self.predict(t) for t in texts]


def _clip01(value: float) -> float:
    """Clamp a float into [0, 1] (schemas require bounded confidence)."""
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(value)))
