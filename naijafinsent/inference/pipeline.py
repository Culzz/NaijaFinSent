"""Inference-time pipeline.

The API depends only on ``AnalysisPipeline`` and the schemas — never on
scikit-learn, transformers, or the training code directly. This keeps the
serving path swappable (a stub for tests, a fine-tuned stack in production).

Stage-wise provenance: every stage records whether it succeeded so an error
can be attributed to parsing, NER, classification, extraction, or resolution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from naijafinsent.config import Settings, get_settings
from naijafinsent.schemas import (
    AnalysisResult,
    EventPrediction,
    ModelRef,
    ProcessingStatus,
    SentimentPrediction,
)
from naijafinsent.utils import sha256_text, utcnow

LIMITATIONS: tuple[str, ...] = (
    "Predictions describe language in published coverage, not fundamentals.",
    "Labels reflect the article text only; coverage may omit context.",
    "Not investment advice. No causal or predictive claim is made.",
    "Confidence is a model estimate and may be miscalibrated on unseen publishers.",
)


@dataclass
class StageProvenance:
    """Which pipeline stages ran and whether each succeeded."""
    stage: str
    ok: bool
    detail: str | None = None
    duration_ms: float | None = None


@dataclass
class PipelineContext:
    stages: list[StageProvenance] = field(default_factory=list)

    def record(self, stage: str, ok: bool, detail: str | None = None,
               duration_ms: float | None = None) -> None:
        self.stages.append(StageProvenance(stage, ok, detail, duration_ms))

    @property
    def all_ok(self) -> bool:
        return all(s.ok for s in self.stages)


class SentimentModel(Protocol):
    def predict(self, text: str) -> SentimentPrediction: ...


class NerModel(Protocol):
    def predict(self, text: str):  # -> list[EntityPrediction]
        ...


class EventModel(Protocol):
    def predict(self, text: str, entities=None):  # -> list[EventPrediction]
        ...


class EntityResolver(Protocol):
    def resolve(self, mentions): ...


class AnalysisPipeline:
    """Wires the models together into a single, auditable analysis run."""

    def __init__(
        self,
        *,
        sentiment_model: SentimentModel | None = None,
        ner_model: NerModel | None = None,
        event_model: EventModel | None = None,
        entity_resolver: EntityResolver | None = None,
        entity_sentiment_fn=None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sentiment_model = sentiment_model
        self.ner_model = ner_model
        self.event_model = event_model
        self.entity_resolver = entity_resolver
        self.entity_sentiment_fn = entity_sentiment_fn
        self.loaded_models: list[str] = []

    # -- introspection the API uses for /models and /health ---------------
    def describe_models(self) -> list[ModelRef]:
        refs: list[ModelRef] = []
        for m in (self.sentiment_model, self.ner_model, self.event_model):
            if m is None:
                continue
            refs.append(
                ModelRef(
                    name=getattr(m, "name", type(m).__name__),
                    version=getattr(m, "version", "unknown"),
                    task=getattr(m, "task", "unknown"),
                    calibrated=bool(getattr(m, "calibrated", False)),
                )
            )
        return refs

    def analyze(self, text: str) -> AnalysisResult:
        ctx = PipelineContext()
        t0 = time.perf_counter()
        started = utcnow()

        # 1. parse / validate
        ctx.record("parse", True, f"{len(text)} chars")
        text = text.strip()

        entities: list = []
        events: list[EventPrediction] = []
        sentiment: SentimentPrediction | None = None
        entity_sentiments: list = []

        # 2. NER
        if self.ner_model is not None:
            s = time.perf_counter()
            try:
                entities = self.ner_model.predict(text)
                ctx.record("ner", True, f"{len(entities)} mentions",
                           (time.perf_counter() - s) * 1000)
            except Exception as exc:  # noqa: BLE001 - provenance, not silence
                ctx.record("ner", False, repr(exc))

        # 3. entity resolution
        if self.entity_resolver is not None and entities:
            s = time.perf_counter()
            try:
                entities = self.entity_resolver.resolve(entities)
                ctx.record("entity_resolution", True,
                           (time.perf_counter() - s) * 1000)
            except Exception as exc:  # noqa: BLE001
                ctx.record("entity_resolution", False, repr(exc))

        # 4. document sentiment
        if self.sentiment_model is not None:
            s = time.perf_counter()
            try:
                sentiment = self.sentiment_model.predict(text)
                ctx.record("sentiment", True, None, (time.perf_counter() - s) * 1000)
            except Exception as exc:  # noqa: BLE001
                ctx.record("sentiment", False, repr(exc))

        # 5. event extraction
        if self.event_model is not None:
            s = time.perf_counter()
            try:
                events = self.event_model.predict(text, entities=entities)
                ctx.record("events", True, f"{len(events)} events",
                           (time.perf_counter() - s) * 1000)
            except Exception as exc:  # noqa: BLE001
                ctx.record("events", False, repr(exc))

        # 6. entity-level sentiment
        if self.entity_sentiment_fn is not None and entities:
            s = time.perf_counter()
            try:
                entity_sentiments = self.entity_sentiment_fn(text, entities)
                ctx.record("entity_sentiment", True, None,
                           (time.perf_counter() - s) * 1000)
            except Exception as exc:  # noqa: BLE001
                ctx.record("entity_sentiment", False, repr(exc))

        if ctx.all_ok:
            status = ProcessingStatus.COMPLETE
        elif any(s.ok for s in ctx.stages):
            status = ProcessingStatus.PARTIAL
        else:
            status = ProcessingStatus.FAILED

        return AnalysisResult(
            text_sha256=sha256_text(text),
            status=status,
            sentiment=sentiment,
            entities=entities,
            entity_sentiments=entity_sentiments,
            events=events,
            limitations=list(LIMITATIONS),
            processed_at=started,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )


class StubPipeline(AnalysisPipeline):
    """Zero-dependency pipeline used by tests and the offline dev server.

    Deterministic, rule-based, and honest about its limitations. Wires the
    deterministic models (lexicon sentiment, rule NER, keyword events) so the
    demo path produces real, evidence-backed predictions with no weights.
    """

    stub_models = True

    def __init__(self, *, settings: Settings | None = None, **kwargs) -> None:
        from naijafinsent.entity_resolution.resolver import EntityResolver
        from naijafinsent.event_extraction.keywords import KeywordEventModel
        from naijafinsent.ner.rules import RuleBasedNer
        from naijafinsent.sentiment.lexicon import LexiconSentimentModel

        super().__init__(
            sentiment_model=LexiconSentimentModel(),
            ner_model=RuleBasedNer(),
            event_model=KeywordEventModel(),
            entity_resolver=EntityResolver(),
            settings=settings,
            **kwargs,
        )
