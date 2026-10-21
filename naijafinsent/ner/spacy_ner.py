"""spaCy NER trained from scratch on our BIO data.

Uses ``spacy.blank("en")`` plus a NER component configured with our entity
types -- no pre-trained pipeline, so nothing is downloaded. ``spacy`` is
imported lazily and guarded; the base package works without it.

Training data is built from ``(text, spans)`` pairs where each span is an
``EntitySpan`` (char offsets), which spaCy consumes directly via
``Example``/``Doc.char_span``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType
from naijafinsent.ner.base import ENTITY_TYPES, BaseNerModel

__all__ = ["SpacyNer", "MISSING_SPACY_MSG"]

MISSING_SPACY_MSG = (
    "SpacyNer requires 'spacy'. Install with: pip install 'naijafinsent[ml]' "
    "(or pip install spacy>=3.7). It is intentionally excluded from the base "
    "install because it is a large optional dependency."
)


def _require_spacy():
    try:
        import spacy  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(MISSING_SPACY_MSG) from exc
    import spacy

    return spacy


class SpacyNer(BaseNerModel):
    """Blank-English spaCy NER with our entity types."""

    name = "spacy-ner"
    version = "0.1.0"
    calibrated = False

    def __init__(self, *, entity_types: Sequence[str] = ENTITY_TYPES) -> None:
        self.entity_types = tuple(entity_types)
        self._nlp = None

    # -- construction ---------------------------------------------------
    def _build_blank(self):
        spacy = _require_spacy()
        nlp = spacy.blank("en")
        if "ner" not in nlp.pipe_names:
            ner = nlp.add_pipe("ner")
        else:
            ner = nlp.get_pipe("ner")
        for et in self.entity_types:
            ner.add_label(et)
        return nlp

    def _make_examples(self, pairs: Iterable[tuple[str, list[EntitySpan]]]):
        spacy = _require_spacy()
        examples = []
        for text, spans in pairs:
            doc = self._nlp.make_doc(text)
            gold = spacy.training.Example.from_dict(
                doc, {"entities": [(s.start, s.end, s.entity_type.value) for s in spans]}
            )
            examples.append(gold)
        return examples

    # -- training -------------------------------------------------------
    def fit(
        self,
        texts: Sequence[str],
        spans: Sequence[list[EntitySpan]],
        *,
        epochs: int = 20,
        batch_size: int = 16,
        dropout: float = 0.2,
        seed: int = 42,
    ) -> SpacyNer:
        spacy = _require_spacy()
        if self._nlp is None:
            self._nlp = self._build_blank()

        examples = self._make_examples(list(zip(texts, spans)))
        optimizer = self._nlp.begin_training()
        data = spacy.util.minibatch(examples, size=batch_size)
        for _ in range(epochs):
            for batch in data:
                self._nlp.update(batch, drop=dropout, sgd=optimizer)
        return self

    # -- inference ------------------------------------------------------
    def predict(self, text: str) -> list[EntityPrediction]:
        if self._nlp is None:
            raise RuntimeError("SpacyNer is not fitted; call fit() or load() first.")
        doc = self._nlp(text)
        out: list[EntityPrediction] = []
        for ent in doc.ents:
            span = EntitySpan(
                start=ent.start_char,
                end=ent.end_char,
                text=ent.text,
                entity_type=EntityType(ent.label_),
            )
            out.append(EntityPrediction(span=span, confidence=0.7, resolution_method=None))
        return out

    # -- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        if self._nlp is None:
            raise RuntimeError("cannot save an unfitted SpacyNer")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._nlp.to_disk(path)

    @classmethod
    def load(cls, path: str | Path) -> SpacyNer:
        model = cls()
        model._nlp = _require_spacy().load(path)
        return model
