"""Model registry loading with an explicit, honest fallback to the stub pipeline.

Contract with the rest of the API
---------------------------------
* The API only ever holds an ``AnalysisPipeline``. Whether its stages are real
  models, partially-real models, or the deterministic stub is reported in the
  returned ``info`` dict and surfaced by ``/health`` and ``/models``.
* **W&B is never imported.** Experiment tracking is a training-time concern; a
  serving container that can fail because an API key expired is a bug.
* **Cold start is bounded and described.** Loading models is synchronous and
  happens once (guarded by the caller's lock). :func:`describe_memory_budget`
  returns an estimate so the deployment doc can say what to expect instead of
  "it depends".

Graceful degradation ladder
---------------------------
1. Registry missing or unreadable        -> StubPipeline, ``source="no_registry"``.
2. Registry parses, no usable entries    -> StubPipeline, ``source="empty_registry"``.
3. Some artifacts fail to load           -> the ones that load are wired in;
   a stage that failed stays ``None`` (pipeline records no stage provenance for
   it and the result is marked PARTIAL), ``source="partial"``.
4. All artifacts load                    -> ``source="registry"``.

The loader never raises on a bad registry. A serving process that refuses to
boot because a JSON file is stale is worse than one that boots and says so.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from naijafinsent.config import Settings, get_settings
from naijafinsent.constants import TASK_EVENTS, TASK_NER, TASK_SENTIMENT
from naijafinsent.inference.pipeline import AnalysisPipeline, StubPipeline

logger = logging.getLogger(__name__)


# Rough, deliberately conservative per-artifact memory estimates in MiB. These
# are for the deployment checklist ("will this fit on a 512MB dyno?"), not for
# capacity planning. A transformer NER/event model loaded on CPU is the large
# term; classical sklearn artifacts are tens of MiB.
_MEMORY_HINTS_MIB: dict[str, int] = {
    "sklearn": 40,
    "joblib": 40,
    "onnx": 120,
    "transformers": 500,
    "spacy": 200,
    "crf": 30,
}


def load_registry(path: Path | str | None) -> list[dict[str, Any]]:
    """Read the registry JSON.

    Accepts either a bare list or ``{"models": [...]}`` so both a hand-written
    file and an exporter output work. Returns ``[]`` for anything unusable.
    """
    if path is None:
        return []
    registry_path = Path(path)
    if not registry_path.exists():
        logger.info("model registry not found at %s", registry_path)
        return []
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("model registry unreadable at %s: %r", registry_path, exc)
        return []

    if isinstance(raw, dict):
        raw = raw.get("models", [])
    if not isinstance(raw, list):
        logger.warning("model registry has unexpected shape: %s", type(raw).__name__)
        return []

    entries = [e for e in raw if isinstance(e, dict) and e.get("path")]
    logger.info("model registry %s lists %d usable entries", registry_path, len(entries))
    return entries


def _import_optional(module_path: str, attr: str) -> Any | None:
    """Import ``attr`` from ``module_path`` without exploding when it is absent.

    The concrete model classes live in the core package's task modules, which
    another agent may still be filling in. Absence is expected during staged
    development and means "fall back", not "crash".
    """
    try:
        module = __import__(module_path, fromlist=[attr])
    except Exception as exc:  # noqa: BLE001
        logger.info("optional model module %s unavailable: %r", module_path, exc)
        return None
    candidate = getattr(module, attr, None)
    if candidate is None:
        logger.info("module %s has no %s", module_path, attr)
    return candidate


def _try_load_sklearn(path: Path) -> Any | None:
    """Load a joblib/pickle artifact. Returns None when the class cannot be built."""
    try:
        import joblib  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        logger.info("joblib unavailable; cannot load %s", path)
        return None
    # We intentionally do not unpickle an arbitrary object and guess its API.
    # A registry entry must name a wrapper class that knows how to predict.
    logger.info(
        "artifact %s is not wired to a known wrapper; leaving the stage unloaded", path
    )
    return None


def _build_stage(entry: dict[str, Any]) -> Any | None:
    """Turn one registry entry into a stage object, or ``None``.

    The registry entry names a ``framework`` and a ``path``. Loading is done via
    the core package's optional wrappers; when those are not present yet we
    return ``None`` so the pipeline degrades to the stub for that stage.
    """
    task = str(entry.get("task", "")).lower()
    framework = str(entry.get("framework", "sklearn")).lower()
    path = Path(str(entry["path"]))
    if not path.exists():
        logger.warning("registry entry for task=%s points at missing path %s", task, path)
        return None

    # Registry entries may name an explicit wrapper class.
    wrapper = entry.get("wrapper")
    if wrapper:
        module_path, _, attr = str(wrapper).partition(":")
        factory = _import_optional(module_path, attr)
        if factory is None:
            return None
        try:
            return factory(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wrapper %s failed for %s: %r", wrapper, path, exc)
            return None

    # Default wrapper names per task, resolved from the core package if present.
    defaults: dict[str, list[tuple[str, str]]] = {
        TASK_SENTIMENT: [
            ("naijafinsent.sentiment.model", "SentimentModel"),
            ("naijafinsent.sentiment", "SentimentModel"),
        ],
        TASK_NER: [
            ("naijafinsent.ner.model", "NerModel"),
            ("naijafinsent.ner", "NerModel"),
        ],
        TASK_EVENTS: [
            ("naijafinsent.event_extraction.model", "EventModel"),
            ("naijafinsent.event_extraction", "EventModel"),
        ],
    }
    for module_path, attr in defaults.get(task, []):
        factory = _import_optional(module_path, attr)
        if factory is None:
            continue
        try:
            return factory(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("default wrapper %s:%s failed: %r", module_path, attr, exc)
    if framework in _MEMORY_HINTS_MIB:
        _try_load_sklearn(path)
    return None


def load_pipeline_from_registry(
    settings: Settings | None = None,
    *,
    registry_path: Path | str | None = None,
) -> tuple[AnalysisPipeline, dict[str, Any]]:
    """Build the best pipeline available. Never raises for a bad registry.

    Returns
    -------
    (pipeline, info)
        ``info`` always contains ``source``, ``stub``, ``models``, ``load_ms``
        and (when applicable) ``warnings``.
    """
    settings = settings or get_settings()
    path = registry_path if registry_path is not None else settings.model_registry_path

    started = time.perf_counter()
    entries = load_registry(path)

    if not entries:
        pipeline = StubPipeline(settings=settings)
        return pipeline, {
            "source": "no_registry" if path is None or not Path(path).exists() else "empty_registry",
            "stub": True,
            "models": _describe(pipeline),
            "load_ms": round((time.perf_counter() - started) * 1000, 2),
            "warnings": [
                "No usable model registry entry found; serving the deterministic stub "
                "pipeline. Predictions are honest but not model-backed."
            ],
            "registry_path": str(path) if path is not None else None,
        }

    sentiment_model = ner_model = event_model = None
    warnings: list[str] = []
    for entry in entries:
        task = str(entry.get("task", "")).lower()
        stage = _build_stage(entry)
        if stage is None:
            warnings.append(
                f"could not load task={task} from {entry.get('path')!r}; "
                "that stage is disabled"
            )
            continue
        if task == TASK_SENTIMENT:
            sentiment_model = stage
        elif task == TASK_NER:
            ner_model = stage
        elif task == TASK_EVENTS:
            event_model = stage
        else:
            warnings.append(f"unknown task {task!r} in registry; ignored")

    if sentiment_model is None and ner_model is None and event_model is None:
        pipeline = StubPipeline(settings=settings)
        return pipeline, {
            "source": "registry_unusable",
            "stub": True,
            "models": _describe(pipeline),
            "load_ms": round((time.perf_counter() - started) * 1000, 2),
            "warnings": warnings
            + ["No registry entry could be loaded; serving the deterministic stub pipeline."],
            "registry_path": str(path),
        }

    pipeline = AnalysisPipeline(
        sentiment_model=sentiment_model,
        ner_model=ner_model,
        event_model=event_model,
        settings=settings,
    )
    pipeline.loaded_models = [
        name
        for name, model in (
            ("sentiment", sentiment_model),
            ("ner", ner_model),
            ("events", event_model),
        )
        if model is not None
    ]
    source = "registry" if len(pipeline.loaded_models) == 3 else "partial"
    return pipeline, {
        "source": source,
        "stub": False,
        "models": _describe(pipeline),
        "load_ms": round((time.perf_counter() - started) * 1000, 2),
        "warnings": warnings,
        "registry_path": str(path),
    }


def _describe(pipeline: AnalysisPipeline) -> list[dict[str, Any]]:
    return [
        {"name": ref.name, "version": ref.version, "task": ref.task, "calibrated": ref.calibrated}
        for ref in pipeline.describe_models()
    ]


def describe_memory_budget(pipeline: AnalysisPipeline) -> str:
    """A rough, explicit memory statement for the deployment checklist.

    We sum conservative per-framework hints rather than measuring RSS, because
    the point is to warn an operator *before* a 512MB host OOM-kills the
    container, not to be precise.
    """
    if isinstance(pipeline, StubPipeline):
        return "StubPipeline: no model weights; memory is dominated by the web server (~50-80 MiB)."
    total = 0
    parts: list[str] = []
    for name, model in (
        ("sentiment", pipeline.sentiment_model),
        ("ner", pipeline.ner_model),
        ("events", pipeline.event_model),
    ):
        if model is None:
            continue
        framework = str(getattr(model, "framework", "sklearn")).lower()
        hint = _MEMORY_HINTS_MIB.get(framework, 50)
        total += hint
        parts.append(f"{name}~{hint}MiB({framework})")
    return (
        f"Estimated resident model memory ~{total} MiB: "
        + ", ".join(parts)
        + ". Cold start loads these synchronously once; budget the first request "
        "for the registry read plus artifact load time."
    )


__all__ = [
    "describe_memory_budget",
    "load_pipeline_from_registry",
    "load_registry",
]
