"""LLM pre-labelling scaffold with a mandatory human-review requirement.

Design rules baked in here:

* **Human review is non-negotiable.** Every record produced by a pre-labeller is
  marked ``model_prelabel=True`` and ``prelabel_records`` refuses to emit a
  record that has no ``reviewed_by``. Pre-labels are never gold.
* **The label space is declared exactly** in the prompt, drawn from
  ``constants.py``, and the model is asked for JSON only.
* **Graceful degradation.** ``AnthropicPrelabeler`` imports ``anthropic`` lazily
  and raises a clear error only when actually called without an API key. With no
  key, ``prelabel_records`` is a no-op that returns the input unchanged.
* **Cost/latency are logged per call** into a ``PrelabelCall`` record.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from naijafinsent.config import Settings, get_settings
from naijafinsent.constants import (
    ENTITY_TYPES,
    EVENT_TYPE_DESCRIPTIONS,
    EVENT_TYPES,
    SENTIMENT_LABELS,
)
from naijafinsent.schemas import (
    AnnotationRecord,
    EntitySpan,
    EntityType,
    EventAnnotation,
    EventType,
    SentimentAnnotation,
    SentimentLabel,
)

# --------------------------------------------------------------------------
# Call bookkeeping
# --------------------------------------------------------------------------

@dataclass
class PrelabelCall:
    """Cost/latency telemetry for one LLM call."""

    item_id: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    ok: bool = True
    error: str | None = None


@dataclass
class PrelabelResult:
    """A single pre-labelled record plus its call telemetry."""

    record: AnnotationRecord
    call: PrelabelCall


# --------------------------------------------------------------------------
# Protocol
# --------------------------------------------------------------------------

class LLMPrelabeler(Protocol):
    """Anything that can propose labels for one text."""

    name: str

    def prelabel(self, text: str, *, item_id: str = "item") -> PrelabelResult: ...


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": list(SENTIMENT_LABELS)},
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "entity_type": {"type": "string", "enum": list(ENTITY_TYPES)},
                },
                "required": ["start", "end", "entity_type"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
                    "evidence_start": {"type": "integer"},
                    "evidence_end": {"type": "integer"},
                },
                "required": ["event_type", "evidence_start", "evidence_end"],
            },
        },
    },
    "required": ["sentiment", "spans", "events"],
}


def build_prompt(text: str) -> str:
    """Build the strict, label-space-exact pre-labelling prompt."""
    entity_lines = "\n".join(f"- {t}" for t in ENTITY_TYPES)
    event_lines = "\n".join(f"- {t}: {EVENT_TYPE_DESCRIPTIONS[t]}" for t in EVENT_TYPES)
    sentiment_lines = "\n".join(f"- {s}" for s in SENTIMENT_LABELS)
    return (
        "You are pre-labelling Nigerian financial news for a human annotator who "
        "WILL review and correct every field. Propose labels only; do not explain.\n\n"
        "Document sentiment labels:\n"
        f"{sentiment_lines}\n"
        "neutral = the text takes no position. uncertain = the text takes a "
        "position but hedges, conditions, or leaves it open. Never use uncertain "
        "to mean you are unsure.\n\n"
        "Entity types (exactly one per span):\n"
        f"{entity_lines}\n\n"
        "Event types:\n"
        f"{event_lines}\n\n"
        "Rules: offsets are inclusive-start/exclusive-end into the text below. "
        "Spans of different types must not overlap. Every event needs an evidence "
        "span. Return JSON only, matching this schema:\n"
        f"{json.dumps(_JSON_SCHEMA)}\n\n"
        "TEXT:\n"
        f"{text}"
    )


# --------------------------------------------------------------------------
# Parsing + validation
# --------------------------------------------------------------------------

def parse_prelabel_json(
    payload: str | dict[str, Any],
    text: str,
    *,
    item_id: str,
    article_id: str | None = None,
    split: str = "train",
    annotator: str = "llm_prelabel",
    reviewed_by: str | None = None,
) -> AnnotationRecord:
    """Parse model JSON into a validated ``AnnotationRecord``.

    Raises ``ValueError`` on malformed output or offsets that do not slice
    cleanly, so a bad pre-label never silently becomes a record.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"pre-label output is not valid JSON: {exc}") from exc
    else:
        data = payload

    if not isinstance(data, dict):
        raise ValueError("pre-label output must be a JSON object")

    sentiment_value = data.get("sentiment")
    if sentiment_value not in SENTIMENT_LABELS:
        raise ValueError(f"invalid sentiment {sentiment_value!r}")

    spans: list[EntitySpan] = []
    for raw in data.get("spans", []) or []:
        start, end = int(raw["start"]), int(raw["end"])
        etype = raw["entity_type"]
        if etype not in ENTITY_TYPES:
            raise ValueError(f"invalid entity_type {etype!r}")
        if start < 0 or end > len(text) or start >= end:
            raise ValueError(f"span offsets [{start}:{end}] out of bounds for {len(text)} chars")
        spans.append(
            EntitySpan(start=start, end=end, text=text[start:end], entity_type=EntityType(etype))
        )

    events: list[EventAnnotation] = []
    for raw in data.get("events", []) or []:
        etype = raw["event_type"]
        if etype not in EVENT_TYPES:
            raise ValueError(f"invalid event_type {etype!r}")
        es, ee = int(raw["evidence_start"]), int(raw["evidence_end"])
        if es < 0 or ee > len(text) or es >= ee:
            raise ValueError(f"evidence offsets [{es}:{ee}] out of bounds")
        evidence = EntitySpan(
            start=es, end=ee, text=text[es:ee], entity_type=EntityType.ORG
        )
        events.append(
            EventAnnotation(
                event_type=EventType(etype),
                evidence_span=evidence,
                annotator=annotator,
                model_prelabel=True,
            )
        )

    sentiment = SentimentAnnotation(
        label=SentimentLabel(sentiment_value),
        annotator=annotator,
        model_prelabel=True,
    )

    return AnnotationRecord(
        item_id=item_id,
        article_id=article_id or item_id,
        split=split,
        text=text,
        sentiment=sentiment,
        spans=spans,
        events=events,
    )


# --------------------------------------------------------------------------
# Anthropic implementation
# --------------------------------------------------------------------------

class AnthropicPrelabeler:
    """Claude-backed pre-labeller. ``anthropic`` is imported lazily."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-3-5-sonnet-latest",
        settings: Settings | None = None,
        max_tokens: int = 2048,
        input_cost_per_mtok: float = 3.0,
        output_cost_per_mtok: float = 15.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model
        self.max_tokens = max_tokens
        self.input_cost_per_mtok = input_cost_per_mtok
        self.output_cost_per_mtok = output_cost_per_mtok
        self.calls: list[PrelabelCall] = []

    @property
    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def prelabel(self, text: str, *, item_id: str = "item") -> PrelabelResult:
        if not self.settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; pre-labelling is disabled. "
                "prelabel_records() degrades to a no-op in this case."
            )
        try:
            import anthropic  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "the 'anthropic' package is not installed; install with "
                "pip install 'naijafinsent[llm]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        prompt = build_prompt(text)
        started = time.perf_counter()
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = (time.perf_counter() - started) * 1000
            raw = "".join(
                block.text for block in message.content if getattr(block, "type", "") == "text"
            )
            usage = getattr(message, "usage", None)
            in_tok = getattr(usage, "input_tokens", None)
            out_tok = getattr(usage, "output_tokens", None)
            cost = None
            if in_tok is not None and out_tok is not None:
                cost = (
                    in_tok / 1e6 * self.input_cost_per_mtok
                    + out_tok / 1e6 * self.output_cost_per_mtok
                )
            record = parse_prelabel_json(raw, text, item_id=item_id, annotator=self.name)
            call = PrelabelCall(
                item_id=item_id,
                latency_ms=latency_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                estimated_cost_usd=cost,
                ok=True,
            )
        except Exception as exc:  # noqa: BLE001 - telemetry, then re-raise
            latency_ms = (time.perf_counter() - started) * 1000
            call = PrelabelCall(item_id=item_id, latency_ms=latency_ms, ok=False, error=repr(exc))
            self.calls.append(call)
            raise

        self.calls.append(call)
        return PrelabelResult(record=record, call=call)

    def cost_summary(self) -> dict[str, float | int]:
        total_cost = sum(c.estimated_cost_usd or 0.0 for c in self.calls)
        total_latency = sum(c.latency_ms for c in self.calls)
        return {
            "n_calls": len(self.calls),
            "n_failed": sum(1 for c in self.calls if not c.ok),
            "total_cost_usd": total_cost,
            "total_latency_ms": total_latency,
        }


# --------------------------------------------------------------------------
# Batch driver
# --------------------------------------------------------------------------

def prelabel_records(
    records: Iterable[AnnotationRecord] | Sequence[str],
    prelabeler: LLMPrelabeler | None,
    *,
    reviewed_by: str | None = None,
    texts: Sequence[str] | None = None,
) -> list[AnnotationRecord]:
    """Pre-label records, enforcing the human-review requirement.

    * When ``prelabeler`` is ``None`` or unavailable (no API key), this is a
      **no-op** that returns the input records unchanged.
    * When ``reviewed_by`` is ``None``, this **raises** — a pre-label may not be
      emitted without naming the human who will review it.
    """
    inputs = list(records)

    def _unavailable() -> bool:
        if prelabeler is None:
            return True
        available = getattr(prelabeler, "available", True)
        return not bool(available)

    if _unavailable():
        # Graceful no-op: return inputs as-is (records) or nothing for raw text.
        return [r for r in inputs if isinstance(r, AnnotationRecord)]

    if reviewed_by is None:
        raise ValueError(
            "reviewed_by is required: LLM pre-labels must be reviewed by a named "
            "human before they can be emitted (see docs/ANNOTATION_GUIDE.md)."
        )

    out: list[AnnotationRecord] = []
    for idx, obj in enumerate(inputs):
        if isinstance(obj, AnnotationRecord):
            text = obj.text
            item_id = obj.item_id
            article_id = obj.article_id
            split = obj.split
        else:
            text = str(obj)
            item_id = f"item_{idx}"
            article_id = item_id
            split = "train"

        result = prelabeler.prelabel(text, item_id=item_id)  # type: ignore[union-attr]
        record = result.record.model_copy(
            update={
                "item_id": item_id,
                "article_id": article_id,
                "split": split,
            }
        )
        # Stamp the human reviewer on every annotation.
        sentiment = record.sentiment
        if sentiment is not None:
            sentiment = sentiment.model_copy(
                update={"model_prelabel": True, "annotator": reviewed_by}
            )
        events = [
            e.model_copy(update={"model_prelabel": True, "annotator": reviewed_by})
            for e in record.events
        ]
        out.append(record.model_copy(update={"sentiment": sentiment, "events": events}))
    return out
