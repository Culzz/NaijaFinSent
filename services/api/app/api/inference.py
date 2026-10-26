"""Inference endpoints: ``/sentiment``, ``/entities``, ``/analyze``.

All three accept ``{text}`` or ``{texts: [...]}``. Batch responses preserve input
order, because a caller pairing inputs to outputs by position should not have to
defend against reordering.
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from naijafinsent.inference.pipeline import AnalysisPipeline, StubPipeline
from naijafinsent.schemas import (
    AnalysisResult,
    EntityPrediction,
    SentimentPrediction,
)
from naijafinsent.utils import sha256_text

from app.api._common import ValidationFailure, request_fingerprint
from app.deps import (
    PipelineDep,
    RateLimitDep,
    SettingsDep,
    get_request_id,
)
from app.schemas import AnalyzeRequest, EntityRequest, SentimentRequest

router = APIRouter(tags=["inference"])

_DISCLAIMER_NOTE = (
    "Predictions describe language in published coverage. They are not investment "
    "advice and make no causal or predictive claim about prices or returns."
)


def _resolve(request_model: Any, settings: Any, request: Request) -> list[str]:
    """Validate the payload shape and limits, raising a 422 envelope on failure."""
    try:
        return request_model.resolve_texts(
            max_text_chars=settings.max_text_chars,
            max_batch_size=settings.max_batch_size,
        )
    except ValueError as exc:
        raise ValidationFailure(str(exc), request=request) from exc


def _sentiment_for(pipeline: AnalysisPipeline, text: str) -> SentimentPrediction:
    """Run document sentiment, or synthesise an honest 'no model' prediction.

    When the pipeline has no sentiment model (a partial registry load or a bare
    ``AnalysisPipeline``), we do NOT invent a label. We return the neutral label
    with zero confidence and a model ref that says ``unavailable``, so a caller
    can distinguish "we think this is neutral" from "we could not score this".
    """
    if pipeline.sentiment_model is None:
        from naijafinsent.schemas import ModelRef, SentimentLabel

        return SentimentPrediction(
            label=SentimentLabel.NEUTRAL,
            confidence=0.0,
            probabilities={},
            evidence=[],
            model=ModelRef(name="unavailable", version="none", task="sentiment", calibrated=False),
        )
    return pipeline.sentiment_model.predict(text)


def _entity_payload(pipeline: AnalysisPipeline, text: str) -> list[EntityPrediction]:
    if pipeline.ner_model is None:
        return []
    entities = pipeline.ner_model.predict(text)
    if pipeline.entity_resolver is not None and entities:
        try:
            entities = pipeline.entity_resolver.resolve(entities)
        except Exception:  # noqa: BLE001 - resolution is best-effort
            pass
    return list(entities)


@router.post(
    "/sentiment",
    summary="Score document-level sentiment",
    description=(
        "Returns a calibrated-as-available sentiment label for one text or a batch. "
        "Enforces max text length, batch size and encoding. "
        + _DISCLAIMER_NOTE
    ),
    dependencies=[RateLimitDep],
)
def post_sentiment(
    request: Request,
    pipeline: PipelineDep,
    settings: SettingsDep,
    body: Annotated[SentimentRequest, Body(...)],
) -> dict[str, Any]:
    texts = _resolve(body, settings, request)
    started = time.perf_counter()
    predictions = [_sentiment_for(pipeline, text) for text in texts]
    latency_ms = round((time.perf_counter() - started) * 1000, 3)

    payload: dict[str, Any] = {
        "status": "complete",
        "count": len(predictions),
        "latency_ms": latency_ms,
        "request_id": get_request_id(request),
        "pipeline": _pipeline_label(pipeline),
        "disclaimer": settings.disclaimer,
    }
    if len(predictions) == 1:
        payload["prediction"] = predictions[0].model_dump(mode="json")
    payload["predictions"] = [p.model_dump(mode="json") for p in predictions]
    return payload


@router.post(
    "/entities",
    summary="Extract and resolve named entities",
    description=(
        "Returns entity spans with offsets and, where resolution succeeded, the "
        "canonical entity id. Unresolved mentions are returned with entity_id=null "
        "rather than being force-linked. " + _DISCLAIMER_NOTE
    ),
    dependencies=[RateLimitDep],
)
def post_entities(
    request: Request,
    pipeline: PipelineDep,
    settings: SettingsDep,
    body: Annotated[EntityRequest, Body(...)],
) -> dict[str, Any]:
    texts = _resolve(body, settings, request)
    started = time.perf_counter()
    results = [_entity_payload(pipeline, text) for text in texts]
    latency_ms = round((time.perf_counter() - started) * 1000, 3)

    if len(results) == 1:
        return {
            "entities": [e.model_dump(mode="json") for e in results[0]],
            "count": len(results[0]),
            "status": "complete",
            "latency_ms": latency_ms,
            "request_id": get_request_id(request),
            "pipeline": _pipeline_label(pipeline),
            "disclaimer": settings.disclaimer,
        }
    return {
        "results": [[e.model_dump(mode="json") for e in group] for group in results],
        "counts": [len(group) for group in results],
        "status": "complete",
        "latency_ms": latency_ms,
        "request_id": get_request_id(request),
        "pipeline": _pipeline_label(pipeline),
        "disclaimer": settings.disclaimer,
    }


@router.post(
    "/analyze",
    response_model=AnalysisResult,
    summary="Run the full analysis pipeline",
    description=(
        "Sentiment + entities + events in one auditable pass, with stage provenance "
        "and the platform's stated limitations. " + _DISCLAIMER_NOTE
    ),
    dependencies=[RateLimitDep],
)
def post_analyze(
    request: Request,
    pipeline: PipelineDep,
    settings: SettingsDep,
    body: Annotated[AnalyzeRequest, Body(...)],
) -> AnalysisResult:
    texts = _resolve(body, settings, request)
    if len(texts) != 1:
        raise ValidationFailure(
            "/analyze accepts a single 'text'; use /sentiment with 'texts' for batches",
            code="single_text_required",
            request=request,
        )
    result = pipeline.analyze(texts[0])
    _record_run(request, settings, result, texts[0])
    return result


def _pipeline_label(pipeline: AnalysisPipeline) -> dict[str, Any]:
    refs = pipeline.describe_models()
    return {
        "stub": isinstance(pipeline, StubPipeline),
        "models": [
            {"name": r.name, "version": r.version, "task": r.task, "calibrated": r.calibrated}
            for r in refs
        ],
    }


def _record_run(request: Request, settings: Any, result: AnalysisResult, text: str) -> None:
    """Best-effort provenance row for an analysis call.

    Never allowed to fail the request: losing an observability row is far less
    bad than returning a 500 for a successful analysis.
    """
    try:
        from app.db.base import session_scope
        from app.db.repositories import RunRepository
        from services.worker.ids import new_run_id

        with session_scope() as session:
            RunRepository(session).record_inference(
                run_id=new_run_id("infer"),
                request_hash=request_fingerprint(text),
                latency_ms=result.latency_ms,
                status=result.status.value,
                endpoint="/analyze",
                stage_provenance=[],
            )
            session.commit()
    except Exception:  # noqa: BLE001 - observability must not break serving
        pass


__all__ = ["router"]
