"""TF-IDF + linear sentiment models -- the honest, fast, reproducible baseline.

Two variants:

* :class:`TfidfSentimentModel` -- word n-grams (1-2) and optional char_wb
  n-grams, sublinear TF, feeding a LogisticRegression (probability-native).
* :class:`TfidfSvmSentimentModel` -- same features into a LinearSVC wrapped in
  ``CalibratedClassifierCV`` so it still produces probabilities.

Both expose ``top_features(n)`` for inspection and joblib persistence. Evidence
for these models is derived from the *actually top-weighted features present in
the text* (see :meth:`_linear_evidence`), which is the model's real explanation
rather than a heuristic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from naijafinsent.preprocessing.text import split_sentences
from naijafinsent.schemas import EvidenceSpan
from naijafinsent.sentiment.base import LABELS, BaseSentimentModel

__all__ = ["TfidfSentimentModel", "TfidfSvmSentimentModel"]


def _build_vectorizer(
    *,
    use_char: bool,
    word_ngram_max: int,
    char_ngram_min: int,
    char_ngram_max: int,
    min_df: int,
    max_features: int | None,
):
    """Construct the feature union (word [+ char_wb]) lazily (needs sklearn)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion

    word = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, word_ngram_max),
        sublinear_tf=True,
        min_df=min_df,
        lowercase=True,
        strip_accents="unicode",
        max_features=max_features,
    )
    if not use_char:
        return word
    char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(char_ngram_min, char_ngram_max),
        sublinear_tf=True,
        min_df=min_df,
        lowercase=True,
        strip_accents="unicode",
        max_features=max_features,
    )
    return FeatureUnion([("word", word), ("char", char)])


class _LinearMixin:
    """Shared machinery for the TF-IDF linear models (vectoriser + evidence)."""

    def top_features(self, n: int = 20) -> dict[str, list[tuple[str, float]]]:
        """Top ``n`` weighted features per class, as ``(feature, weight)``.

        For a FeatureUnion the feature names are concatenated in order; we map
        indices back through the fitted vectoriser's ``get_feature_names_out``.
        """
        names = self._feature_names()
        out: dict[str, list[tuple[str, float]]] = {}
        coefs = self._coef_matrix()
        for cls, row in zip(self.labels, coefs):
            order = np.argsort(row)[::-1][:n]
            out[cls] = [(names[i], float(row[i])) for i in order]
        return out

    def _feature_names(self) -> list[str]:
        vec = self.pipeline.named_steps["features"]
        if hasattr(vec, "get_feature_names_out"):
            return list(vec.get_feature_names_out())
        names: list[str] = []
        for _name, sub in vec.transformer_list:
            names.extend(f"{_name}__{f}" for f in sub.get_feature_names_out())
        return names

    def _coef_matrix(self) -> np.ndarray:
        """Return a ``(n_classes, n_features)`` coefficient matrix."""
        clf = self.pipeline.named_steps["clf"]
        # CalibratedClassifierCV wraps the real estimator.
        if hasattr(clf, "calibrated_classifiers_"):
            rows = []
            for cc in clf.calibrated_classifiers_:
                est = cc.estimator
                rows.append(np.asarray(est.coef_).ravel())
            return np.vstack(rows)
        coef = np.asarray(clf.coef_)
        if coef.ndim == 1:
            coef = np.vstack([-coef, coef])
        return coef

    def _linear_evidence(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        """Evidence from the top weighted *n-grams present in this text*.

        Method (honest): we take the model's coefficient row for the predicted
        class, score every feature that the fitted vectoriser actually fires on
        for ``text``, and pick the highest-scoring word n-grams. We then map
        those n-grams back to sentence windows containing them. This is the
        standard linear-model explanation -- it reflects the model, not ground
        truth about cause.
        """
        try:
            names = self._feature_names()
            coefs = dict(zip(self.labels, self._coef_matrix()))
            row = coefs.get(label)
            if row is None:
                return self._fallback_evidence(text)
            feature_vec = self.pipeline.named_steps["features"].transform([text])
            if hasattr(feature_vec, "tocoo"):
                coo = feature_vec.tocoo()
            else:
                coo = feature_vec.tocoo()
            present = coo.col
            scores = [(names[c], float(row[c])) for c in present if c < len(names)]
            scores.sort(key=lambda kv: kv[1], reverse=True)
            # Keep only word-ish features (skip char n-gram indices we cannot
            # map back to text).
            positives = [s for s, sc in scores if sc > 0 and _is_word_feature(s)][:k]
            if not positives:
                positives = [s for s, _ in scores if _is_word_feature(s)][:k]
            spans = self._ngrams_to_spans(text, positives, k)
            return spans or self._fallback_evidence(text)
        except Exception:
            return self._fallback_evidence(text)

    def _ngrams_to_spans(self, text: str, ngrams: list[str], k: int) -> list[EvidenceSpan]:
        """Map feature strings to sentence spans that contain them."""
        spans: list[EvidenceSpan] = []
        seen: set[int] = set()
        sentences = split_sentences(text) or [text]
        cursor = 0
        sent_spans: list[EvidenceSpan] = []
        for s in sentences:
            idx = text.find(s, cursor)
            if idx < 0:
                idx = text.find(s)
            sent_spans.append(EvidenceSpan(text=s, start=idx, end=idx + len(s)))
            cursor = idx + len(s)

        for ng in ngrams:
            token = ng.split("__")[-1]
            token_l = token.lower().replace("_", " ")
            for sp in sent_spans:
                if token_l in sp.text.lower() and sp.start not in seen:
                    spans.append(sp)
                    seen.add(sp.start)
                    break
            if len(spans) >= k:
                break
        return spans


def _is_word_feature(feature_name: str) -> bool:
    """True if the feature name looks like a word/word-ngram (not a char n-gram)."""
    token = feature_name.split("__")[-1]
    if "__" not in feature_name:
        # Single word vectoriser: names are words.
        return True
    # FeatureUnion: prefix tells us the branch.
    branch = feature_name.split("__", 1)[0]
    return branch == "word"


class TfidfSentimentModel(_LinearMixin, BaseSentimentModel):
    """TF-IDF (word 1-2 grams, optional char_wb) + LogisticRegression."""

    name = "tfidf-logreg"

    def __init__(
        self,
        *,
        use_char: bool = False,
        word_ngram_max: int = 2,
        char_ngram_min: int = 3,
        char_ngram_max: int = 5,
        min_df: int = 1,
        max_features: int | None = None,
        C: float = 1.0,
        class_weight: str | dict | None = "balanced",
        max_iter: int = 1000,
        random_state: int = 42,
        calibrated: bool = True,
        version: str = "0.1.0",
    ) -> None:
        self.use_char = use_char
        self.word_ngram_max = word_ngram_max
        self.char_ngram_min = char_ngram_min
        self.char_ngram_max = char_ngram_max
        self.min_df = min_df
        self.max_features = max_features
        self.C = C
        self.class_weight = class_weight
        self.max_iter = max_iter
        self.random_state = random_state
        # LogisticRegression is probability-native, so we treat it as calibrated
        # out of the box (softmax outputs). Honest caveat: it is *not*
        # temperature-tuned unless `calibrated=True` after calibration.py runs.
        self.calibrated = calibrated
        self.version = version
        self.pipeline = None
        self._fitted = False

    def _make_pipeline(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        features = _build_vectorizer(
            use_char=self.use_char,
            word_ngram_max=self.word_ngram_max,
            char_ngram_min=self.char_ngram_min,
            char_ngram_max=self.char_ngram_max,
            min_df=self.min_df,
            max_features=self.max_features,
        )
        clf = LogisticRegression(
            C=self.C,
            class_weight=self.class_weight,
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        return Pipeline([("features", features), ("clf", clf)])

    def fit(self, texts: Sequence[str], labels: Sequence[str], **kwargs) -> TfidfSentimentModel:
        if not texts:
            raise ValueError("fit() requires at least one training example")
        self.pipeline = self._make_pipeline()
        self.pipeline.fit(list(texts), list(labels))
        self._fitted = True
        return self

    def predict_proba(self, text: str) -> dict[str, float]:
        if not self._fitted:
            return {lab: 1.0 / len(self.labels) for lab in self.labels}
        proba = self.pipeline.predict_proba([text])[0]
        classes = list(self.pipeline.named_steps["clf"].classes_)
        dist = {lab: 0.0 for lab in self.labels}
        for cls, p in zip(classes, proba):
            dist[str(cls)] = float(p)
        return dist

    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        if not self._fitted:
            return self._fallback_evidence(text)
        return self._linear_evidence(text, label, k=k)

    def predict_batch(self, texts: Sequence[str]):
        if not self._fitted:
            return super().predict_batch(texts)
        proba = self.pipeline.predict_proba(list(texts))
        classes = list(self.pipeline.named_steps["clf"].classes_)
        out = []
        for row in proba:
            dist = {lab: 0.0 for lab in self.labels}
            for cls, p in zip(classes, row):
                dist[str(cls)] = float(p)
            label = max(dist.items(), key=lambda kv: kv[1])[0]
            evidence = self.explain(texts[len(out)], label)
            out.append(self._build_prediction(label, dist, evidence))
        return out

    # -- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        import joblib

        if not self._fitted:
            raise RuntimeError("cannot save an unfitted model")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pipeline": self.pipeline,
                "config": self._config(),
                "labels": self.labels,
                "version": self.version,
                "calibrated": self.calibrated,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> TfidfSentimentModel:
        import joblib

        blob = joblib.load(Path(path))
        model = cls(**blob.get("config", {}))
        model.pipeline = blob["pipeline"]
        model.version = blob.get("version", model.version)
        model.calibrated = blob.get("calibrated", model.calibrated)
        model._fitted = True
        return model

    def _config(self) -> dict:
        return {
            "use_char": self.use_char,
            "word_ngram_max": self.word_ngram_max,
            "char_ngram_min": self.char_ngram_min,
            "char_ngram_max": self.char_ngram_max,
            "min_df": self.min_df,
            "max_features": self.max_features,
            "C": self.C,
            "class_weight": self.class_weight,
            "max_iter": self.max_iter,
            "random_state": self.random_state,
            "calibrated": self.calibrated,
            "version": self.version,
        }


class TfidfSvmSentimentModel(_LinearMixin, BaseSentimentModel):
    """TF-IDF (word 1-2 grams, optional char_wb) + LinearSVC.

    LinearSVC has no ``predict_proba``, so it is wrapped in
    ``CalibratedClassifierCV`` (sigmoid/Platt by default) to yield probabilities.
    """

    name = "tfidf-linearsvm"

    def __init__(
        self,
        *,
        use_char: bool = False,
        word_ngram_max: int = 2,
        char_ngram_min: int = 3,
        char_ngram_max: int = 5,
        min_df: int = 1,
        max_features: int | None = None,
        C: float = 1.0,
        class_weight: str | dict | None = "balanced",
        calibration_method: str = "sigmoid",
        cv: int = 3,
        random_state: int = 42,
        calibrated: bool = True,
        version: str = "0.1.0",
    ) -> None:
        self.use_char = use_char
        self.word_ngram_max = word_ngram_max
        self.char_ngram_min = char_ngram_min
        self.char_ngram_max = char_ngram_max
        self.min_df = min_df
        self.max_features = max_features
        self.C = C
        self.class_weight = class_weight
        self.calibration_method = calibration_method
        self.cv = cv
        self.random_state = random_state
        self.calibrated = calibrated
        self.version = version
        self.pipeline = None
        self._fitted = False

    def _make_pipeline(self):
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.linear_model import LinearSVC
        from sklearn.pipeline import Pipeline

        features = _build_vectorizer(
            use_char=self.use_char,
            word_ngram_max=self.word_ngram_max,
            char_ngram_min=self.char_ngram_min,
            char_ngram_max=self.char_ngram_max,
            min_df=self.min_df,
            max_features=self.max_features,
        )
        svc = LinearSVC(
            C=self.C,
            class_weight=self.class_weight,
            random_state=self.random_state,
        )
        clf = CalibratedClassifierCV(
            svc, method=self.calibration_method, cv=self.cv
        )
        return Pipeline([("features", features), ("clf", clf)])

    def fit(self, texts: Sequence[str], labels: Sequence[str], **kwargs) -> TfidfSvmSentimentModel:
        if not texts:
            raise ValueError("fit() requires at least one training example")
        self.pipeline = self._make_pipeline()
        self.pipeline.fit(list(texts), list(labels))
        self._fitted = True
        return self

    def predict_proba(self, text: str) -> dict[str, float]:
        if not self._fitted:
            return {lab: 1.0 / len(self.labels) for lab in self.labels}
        proba = self.pipeline.predict_proba([text])[0]
        # CalibratedClassifierCV exposes classes_ on itself.
        classes = list(self.pipeline.named_steps["clf"].classes_)
        dist = {lab: 0.0 for lab in self.labels}
        for cls, p in zip(classes, proba):
            dist[str(cls)] = float(p)
        return dist

    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        if not self._fitted:
            return self._fallback_evidence(text)
        return self._linear_evidence(text, label, k=k)

    def save(self, path: str | Path) -> None:
        import joblib

        if not self._fitted:
            raise RuntimeError("cannot save an unfitted model")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pipeline": self.pipeline,
                "config": self._config(),
                "labels": self.labels,
                "version": self.version,
                "calibrated": self.calibrated,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> TfidfSvmSentimentModel:
        import joblib

        blob = joblib.load(Path(path))
        model = cls(**blob.get("config", {}))
        model.pipeline = blob["pipeline"]
        model.version = blob.get("version", model.version)
        model.calibrated = blob.get("calibrated", model.calibrated)
        model._fitted = True
        return model

    def _config(self) -> dict:
        return {
            "use_char": self.use_char,
            "word_ngram_max": self.word_ngram_max,
            "char_ngram_min": self.char_ngram_min,
            "char_ngram_max": self.char_ngram_max,
            "min_df": self.min_df,
            "max_features": self.max_features,
            "C": self.C,
            "class_weight": self.class_weight,
            "calibration_method": self.calibration_method,
            "cv": self.cv,
            "random_state": self.random_state,
            "calibrated": self.calibrated,
            "version": self.version,
        }
