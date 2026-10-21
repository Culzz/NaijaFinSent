"""Shared interface for NER models.

Mirrors ``sentiment/base.py``: subclasses set ``name``/``version``/``calibrated``
and implement :meth:`predict`, returning ``list[EntityPrediction]``. ``task`` is
always ``"ner"``. The ``BIO`` scheme constants live here so every tagger agrees
on the tag alphabet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from naijafinsent.constants import ENTITY_TYPES, TASK_NER
from naijafinsent.schemas import EntityPrediction, ModelRef

__all__ = ["BaseNerModel", "BIO", "ENTITY_TYPES"]

#: The entity types we tag (from constants).
ENTITY_TYPES: tuple[str, ...] = ENTITY_TYPES


class BIO:
    """The BIO tag alphabet.

    Tags are ``O`` plus ``B-<TYPE>``/``I-<TYPE>`` for every entity type in
    ``constants.ENTITY_TYPES``. Kept as a class of constants (not an enum) so
    tag strings are directly usable as model labels.
    """

    O = "O"

    @staticmethod
    def begin(entity_type: str) -> str:
        return f"B-{entity_type}"

    @staticmethod
    def inside(entity_type: str) -> str:
        return f"I-{entity_type}"

    @classmethod
    def all_tags(cls) -> list[str]:
        """Complete ordered tag alphabet: ``O`` then B-/I- per entity type."""
        tags = [cls.O]
        for et in ENTITY_TYPES:
            tags.append(cls.begin(et))
            tags.append(cls.inside(et))
        return tags

    @staticmethod
    def parse(tag: str) -> tuple[str, str | None]:
        """Split a tag into ``(prefix, entity_type)``; ``O`` -> ``("O", None)``."""
        if tag == BIO.O or "-" not in tag:
            return (BIO.O, None)
        prefix, _, entity_type = tag.partition("-")
        return (prefix, entity_type)


class BaseNerModel(ABC):
    """Abstract NER model."""

    name: str = "base-ner"
    version: str = "0.0.0"
    task: str = TASK_NER
    #: True only when span confidences are calibrated on held-out data.
    calibrated: bool = False
    entity_types: tuple[str, ...] = ENTITY_TYPES

    @abstractmethod
    def predict(self, text: str) -> list[EntityPrediction]:
        """Return entity mentions in ``text``, with char-offset spans."""

    def fit(self, texts: Sequence[str], spans: Sequence[list], **kwargs) -> BaseNerModel:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement fit(); it is rule/pretrained."
        )

    def save(self, path) -> None:  # noqa: ANN001
        raise NotImplementedError(f"{type(self).__name__} does not implement save()")

    @classmethod
    def load(cls, path) -> BaseNerModel:  # noqa: ANN001
        raise NotImplementedError(f"{cls.__name__} does not implement load()")

    def model_ref(self) -> ModelRef:
        return ModelRef(
            name=self.name,
            version=self.version,
            task=self.task,
            calibrated=self.calibrated,
        )

    def predict_batch(self, texts: Sequence[str]) -> list[list[EntityPrediction]]:
        return [self.predict(t) for t in texts]
