"""TF-IDF event classifier baseline.

One-vs-rest linear classifiers over TF-IDF features, with per-type probability
and an evidence sentence chosen by feature weight. Trained models are small and
CPU-fast, which makes this the honest default when no GPU is available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from naijafinsent.constants import EVENT_TYPES
from naijafinsent.event_extraction.base import EVENT_LABELS, EventModelMixin
from naijafinsent.event_extraction.keywords import KeywordEventModel
from naijafinsent.schemas import (
    EventPrediction,
    EventType,
    EvidenceSpan,
    ModelRef,
)


class EventClassifier(EventModelMixin):
    """Multi-label TF-IDF + logistic regression event classifier."""

    name = "tfidf-events"
    version = "0.1.0"
    task = "events"
    calibrated = False

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        labels: tuple[str, ...] = EVENT_LABELS,
        max_features: int = 30_000,
    ) -> None:
        self.labels = tuple(labels)
        self.threshold = threshold
        self.max_features = max_features
        self._models: dict[str, Pipeline] = {}
        self._fallback = KeywordEventModel()

    # -- training --------------------------------------------------------
    def fit(
        self,
        texts: list[str],
        labels: list[list[str]],
        *,
        seed: int = 0,
    ) -> "EventClassifier":
        """Fit one binary classifier per event type.

        ``labels[i]`` is the list of event types present in ``texts[i]``.
        """
        if len(texts) != len(labels):
            raise ValueError("texts and labels must have the same length")
        y_all = [set(row) for row in labels]
        for label in self.labels:
            y = np.array([1 if label in row else 0 for row in y_all])
            if y.sum() == 0:
                continue  # no examples: keep the rule fallback for this type
            if y.sum() == len(y):
                # Constant class: a trivial "always" model, documented.
                pipe = Pipeline(
                    [
                        ("tfidf", TfidfVectorizer(max_features=self.max_features)),
                        ("clf", LogisticRegression(max_iter=1000, random_state=seed)),
                    ]
                )
            else:
                pipe = Pipeline(
                    [
                        (
                            "tfidf",
                            TfidfVectorizer(
                                max_features=self.max_features,
                                ngram_range=(1, 2),
                                sublinear_tf=True,
                                min_df=1,
                            ),
                        ),
                        (
                            "clf",
                            LogisticRegression(
                                max_iter=1000,
                                class_weight="balanced",
                                random_state=seed,
                            ),
                        ),
                    ]
                )
            pipe.fit(texts, y)
            self._models[label] = pipe
        return self

    # -- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"models": self._models, "labels": self.labels, "threshold": self.threshold},
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "EventClassifier":
        blob = joblib.load(path)
        obj = cls(labels=tuple(blob["labels"]), threshold=blob["threshold"])
        obj._models = blob["models"]
        return obj

    # -- inference -------------------------------------------------------
    def _sentence_spans(self, text: str) -> list[tuple[int, int, str]]:
        return KeywordEventModel._sentences(text)

    def predict(
        self,
        text: str,
        entities=None,  # noqa: ANN001 - part of the pipeline protocol
    ) -> list[EventPrediction]:
        if not text or not text.strip():
            return []
        sentences = self._sentence_spans(text)
        if not sentences:
            return []

        # Sentence-level scores so evidence is always locatable.
        sent_texts = [s[2] for s in sentences]
        out: list[EventPrediction] = []

        for label in self.labels:
            pipe = self._models.get(label)
            if pipe is None:
                continue
            try:
                probs = pipe.predict_proba(sent_texts)[:, 1]
            except Exception:  # noqa: BLE001 - constant classes have no proba
                probs = np.array(
                    [float(pipe.predict([s])[0]) for s in sent_texts]
                )
            best = int(np.argmax(probs))
            if probs[best] >= self.threshold:
                start, end, _ = sentences[best]
                out.append(
                    EventPrediction(
                        event_type=EventType(label),
                        confidence=round(float(probs[best]), 4),
                        entities=[],
                        evidence=[EvidenceSpan(text=text[start:end], start=start, end=end)],
                        attributes={"trigger": "tfidf"},
                        model=ModelRef(
                            name=self.name, version=self.version, task=self.task,
                            calibrated=False,
                        ),
                    )
                )

        # If the trained model produced nothing at all, fall back to rules so
        # the demo path still yields events. This is disclosed in attributes.
        if not out:
            return self._fallback.predict(text, entities)
        return out


__all__ = ["EventClassifier", "EVENT_TYPES"]
