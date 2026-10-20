"""Export the label space to annotation tools, derived from ``constants.py``.

Label Studio and Doccano are configured *from* the shared vocabularies rather
than from hand-maintained config files, so the tools can never drift from
``SENTIMENT_LABELS`` / ``ENTITY_TYPES`` / ``EVENT_TYPES``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from naijafinsent.annotation.guidelines import (
    ENTITY_TYPE_DESCRIPTIONS,
    SENTIMENT_TARGET_DESCRIPTIONS,
    VALIDATION_CONSTANTS,
)
from naijafinsent.constants import (
    ENTITY_TYPES,
    EVENT_TYPE_DESCRIPTIONS,
    EVENT_TYPES,
    SENTIMENT_LABELS,
)
from naijafinsent.schemas import AnnotationRecord

Tool = Literal["label_studio", "doccano"]

# Colour palette so every label is visually distinct in both tools.
_COLOURS: dict[str, str] = {
    "positive": "#2E7D32",
    "negative": "#C62828",
    "neutral": "#616161",
    "uncertain": "#F9A825",
    "ORG": "#1565C0",
    "PER": "#6A1B9A",
    "REGULATOR": "#00838F",
    "MONEY": "#EF6C00",
    "TICKER": "#283593",
    "CURRENCY": "#AD1457",
    "SECTOR": "#558B2F",
    "EVENT_TRIGGER": "#4E342E",
}

_DEFAULT_COLOUR = "#455A64"


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def label_studio_config(
    *,
    text_field: str = "text",
    include_events: bool = True,
) -> str:
    """Return a Label Studio labelling-config XML string.

    The config exposes document sentiment (single choice), NER (span labels),
    and — when ``include_events`` — event classification as a per-region
    choice on the evidence span.
    """
    sentiment_choices = "\n".join(
        '      <Choice value="{v}" style="background: {c}"/>'.format(
            v=_xml_escape(label), c=_COLOURS.get(label, _DEFAULT_COLOUR)
        )
        for label in SENTIMENT_LABELS
    )
    entity_labels = "\n".join(
        '      <Label value="{v}" background="{c}"/>'.format(
            v=_xml_escape(t), c=_COLOURS.get(t, _DEFAULT_COLOUR)
        )
        for t in ENTITY_TYPES
    )
    money_labels = "\n".join(
        '      <Label value="{v}" background="{c}"/>'.format(
            v=_xml_escape(t), c=_COLOURS.get(t, _DEFAULT_COLOUR)
        )
        for t in ENTITY_TYPES
        if t in ("MONEY", "CURRENCY", "TICKER")
    )

    lines: list[str] = ['<View>']
    lines.append(f'  <Text name="{_xml_escape(text_field)}" value="${_xml_escape(text_field)}"/>')
    lines.append(
        '  <Header value="Document sentiment (position on the subject, not the mood)"/>'
    )
    lines.append('  <Choices name="sentiment" toName="%s" choice="single">' % _xml_escape(text_field))
    lines.append(sentiment_choices)
    lines.append("  </Choices>")
    lines.append('  <Header value="Entities (one primary type per span)"/>')
    lines.append('  <Labels name="ner" toName="%s">' % _xml_escape(text_field))
    lines.append(entity_labels)
    lines.append("  </Labels>")
    lines.append('  <Header value="Money normalisation (value/unit/currency — never infer)"/>')
    lines.append('  <Labels name="money" toName="%s">' % _xml_escape(text_field))
    lines.append(money_labels)
    lines.append("  </Labels>")

    if include_events:
        event_choices = "\n".join(
            '      <Choice value="{v}" title="{d}"/>'.format(
                v=_xml_escape(ev), d=_xml_escape(EVENT_TYPE_DESCRIPTIONS.get(ev, ev))
            )
            for ev in EVENT_TYPES
        )
        lines.append('  <Header value="Events (attach to the evidence span)"/>')
        lines.append(
            '  <Choices name="event_type" toName="%s" choice="multiple" perRegion="true">'
            % _xml_escape(text_field)
        )
        lines.append(event_choices)
        lines.append("  </Choices>")

    lines.append("</View>")
    return "\n".join(lines) + "\n"


def doccano_config() -> dict[str, Any]:
    """Return a Doccano-compatible label config.

    Doccano expects ``{"labels": [...]}`` for sequence labelling and a
    ``{"categories": [...]}`` block for document classification. We emit both
    under one document so a single file drives either project type.
    """
    return {
        "labels": list(ENTITY_TYPES),
        "categories": list(EVENT_TYPES),
        "sentiment_labels": list(SENTIMENT_LABELS),
        "entity_descriptions": dict(ENTITY_TYPE_DESCRIPTIONS),
        "event_descriptions": dict(EVENT_TYPE_DESCRIPTIONS),
        "sentiment_target_descriptions": dict(SENTIMENT_TARGET_DESCRIPTIONS),
        "validation": {
            "min_span_chars": VALIDATION_CONSTANTS["min_span_chars"],
            "max_span_chars": VALIDATION_CONSTANTS["max_span_chars"],
            "allow_span_overlap": VALIDATION_CONSTANTS["allow_span_overlap"],
        },
    }


def _record_to_task(record: AnnotationRecord) -> dict[str, Any]:
    """Lightweight task dict for tool import (no ground-truth labels)."""
    return {
        "id": record.item_id,
        "article_id": record.article_id,
        "split": record.split,
        "text": record.text,
        "meta": {"article_id": record.article_id, "split": record.split},
    }


def _coerce_task(obj: AnnotationRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(obj, AnnotationRecord):
        return _record_to_task(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(
        f"expected AnnotationRecord or dict, got {type(obj).__name__}"
    )


def export_tasks(
    records: Iterable[AnnotationRecord | dict[str, Any]],
    path: str | Path,
    *,
    tool: Tool = "label_studio",
) -> int:
    """Write task-import JSONL and return the number of tasks written.

    ``label_studio`` tasks use ``{"data": {"text": ...}, "meta": {...}}``;
    ``doccano`` tasks use ``{"text": ..., "meta": {...}}`` flat.
    """
    if tool not in ("label_studio", "doccano"):
        raise ValueError(f"unknown tool: {tool!r}")

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for obj in records:
            task = _coerce_task(obj)
            text = task.get("text", "")
            meta = task.get("meta", {})
            item_id = task.get("id", task.get("item_id"))
            if tool == "label_studio":
                row = {"data": {"text": text}, "meta": meta}
                if item_id is not None:
                    row["id"] = item_id
            else:
                row = {"text": text, "meta": meta}
                if item_id is not None:
                    row["id"] = item_id
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_tool_configs(directory: str | Path) -> dict[str, Path]:
    """Write both tool configs to ``directory`` and return the paths."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    ls_path = out / "label_studio_config.xml"
    dc_path = out / "doccano_config.json"
    ls_path.write_text(label_studio_config(), encoding="utf-8")
    dc_path.write_text(json.dumps(doccano_config(), indent=2), encoding="utf-8")
    return {"label_studio": ls_path, "doccano": dc_path}
