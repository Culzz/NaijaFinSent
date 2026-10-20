"""Import/export adapters between annotation tools and ``AnnotationRecord``.

Two directions:

* **Import** — Label Studio JSON export and Doccano JSONL export become
  ``AnnotationRecord`` objects.
* **Export** — ``AnnotationRecord`` lists become training-ready JSONL for four
  tasks: document sentiment classification, token classification (BIO), event
  classification, and entity sentiment.

The BIO converter is offset-safe: it tokenises with a simple whitespace +
punctuation tokenizer, aligns character offsets back to tokens, and asserts the
tokens reconstruct the source text exactly.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal

from naijafinsent.constants import (
    TASK_ENTITY_SENTIMENT,
    TASK_EVENTS,
    TASK_NER,
    TASK_SENTIMENT,
)
from naijafinsent.schemas import (
    AnnotationRecord,
    EntitySpan,
    EntityType,
    EventAnnotation,
    EventType,
    MoneyAnnotation,
    SentimentAnnotation,
    SentimentLabel,
)

# --------------------------------------------------------------------------
# Tokenisation (offset-safe)
# --------------------------------------------------------------------------

# A token is a run of non-space characters, split at punctuation boundaries so
# the tokenizer is closer to spaCy than a pure whitespace split. This is
# deliberately dependency-free: tests assert tokens reconstruct the text.
_PUNCT = set(".,;:!?()[]{}\"'`“”‘’—–-/\\|@#$%^&*+=<>~")


def tokenize_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Tokenise ``text`` into ``(token, start, end)`` with char offsets.

    Tokens are either runs of word characters (letters/digits/underscore) or
    single punctuation characters. Joining the tokens with the original
    inter-token text reconstructs ``text`` exactly — we verify this by
    re-slicing, so offsets are guaranteed correct.
    """
    tokens: list[tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _PUNCT:
            tokens.append((ch, i, i + 1))
            i += 1
            continue
        # word run: consume while not space and not punctuation
        j = i
        while j < n and not text[j].isspace() and text[j] not in _PUNCT:
            j += 1
        tokens.append((text[i:j], i, j))
        i = j
    return tokens


def _assert_offsets(text: str, tokens: list[tuple[str, int, int]]) -> None:
    """Verify token offsets slice back to the token strings."""
    for tok, start, end in tokens:
        if start < 0 or end > len(text) or start >= end:
            raise AssertionError(f"token {tok!r} has bad offsets [{start}:{end}]")
        if text[start:end] != tok:
            raise AssertionError(
                f"token {tok!r} does not match text[{start}:{end}]={text[start:end]!r}"
            )


def spans_to_bio(
    text: str,
    spans: Iterable[EntitySpan],
    *,
    tokens: list[tuple[str, int, int]] | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(tokens, tags)`` in BIO form for the given entity spans.

    Alignment is by character overlap between a token and a span. When several
    spans touch a token, the span with the greatest overlap wins; ties break
    toward the longer, then the earlier, span, so the output is deterministic.
    """
    if tokens is None:
        tokens = tokenize_with_offsets(text)
    _assert_offsets(text, tokens)

    # Normalise spans and index by (start, end) so ties resolve deterministically.
    norm_spans: list[EntitySpan] = []
    for span in spans:
        if span.end <= span.start:
            continue
        norm_spans.append(span)
    norm_spans.sort(key=lambda s: (s.start, -s.end))

    tags = ["O"] * len(tokens)
    # Assigned spans, to prevent two spans writing the same token.
    assigned: list[EntitySpan | None] = [None] * len(tokens)

    for ti, (_tok, t_start, t_end) in enumerate(tokens):
        best: EntitySpan | None = None
        best_overlap = 0
        for span in norm_spans:
            overlap = min(t_end, span.end) - max(t_start, span.start)
            if overlap <= 0:
                continue
            if overlap > best_overlap or (
                overlap == best_overlap
                and best is not None
                and (span.end - span.start) > (best.end - best.start)
            ):
                best = span
                best_overlap = overlap
        assigned[ti] = best

    # Emit BIO: B- when the previous assigned span differs, else I-.
    for ti, span in enumerate(assigned):
        if span is None:
            tags[ti] = "O"
            continue
        etype = getattr(span.entity_type, "value", span.entity_type)
        prev = assigned[ti - 1] if ti > 0 else None
        same = prev is not None and prev.start == span.start and prev.end == span.end
        tags[ti] = ("I-" if same else "B-") + etype

    token_strs = [t[0] for t in tokens]
    return token_strs, tags


def bio_to_spans(
    tokens: list[str],
    tags: list[str],
    text: str,
) -> list[EntitySpan]:
    """Reconstruct entity spans from BIO tags by re-deriving offsets.

    ``tokens`` must reconstruct ``text`` in order (whitespace between tokens is
    re-inserted by scanning). Used for round-trip tests.
    """
    if len(tokens) != len(tags):
        raise ValueError("tokens and tags must be the same length")

    # Recover offsets by scanning the text for each token in order.
    spans: list[EntitySpan] = []
    cursor = 0
    current: dict[str, Any] | None = None

    for tok, tag in zip(tokens, tags, strict=True):
        idx = text.find(tok, cursor)
        if idx < 0:
            raise ValueError(f"token {tok!r} not found in text at/after {cursor}")
        start, end = idx, idx + len(tok)
        cursor = end

        if tag == "O":
            if current is not None:
                spans.append(_make_span(text, current))
                current = None
            continue

        prefix, _, etype = tag.partition("-")
        if prefix == "B" or current is None:
            if current is not None:
                spans.append(_make_span(text, current))
            current = {"start": start, "end": end, "type": etype}
        else:  # I- continuation
            if current["type"] != etype:
                spans.append(_make_span(text, current))
                current = {"start": start, "end": end, "type": etype}
            else:
                current["end"] = end

    if current is not None:
        spans.append(_make_span(text, current))
    return spans


def _make_span(text: str, current: dict[str, Any]) -> EntitySpan:
    start, end = current["start"], current["end"]
    return EntitySpan(
        start=start,
        end=end,
        text=text[start:end],
        entity_type=EntityType(current["type"]),
    )


# --------------------------------------------------------------------------
# Label Studio import
# --------------------------------------------------------------------------

def _ls_span_from_result(result: dict[str, Any], text: str) -> EntitySpan | None:
    value = result.get("value", {})
    start = value.get("start")
    end = value.get("end")
    labels = value.get("labels") or []
    if start is None or end is None or not labels:
        return None
    entity_type = labels[0]
    if entity_type not in {t.value for t in EntityType}:
        return None
    return EntitySpan(start=int(start), end=int(end), text=text[int(start) : int(end)],
                      entity_type=EntityType(entity_type))


def label_studio_to_records(
    payload: Any,
    *,
    split: str = "train",
    text_key: str = "text",
) -> list[AnnotationRecord]:
    """Convert a Label Studio JSON export into ``AnnotationRecord`` objects."""
    tasks = payload
    if isinstance(payload, dict):
        tasks = payload.get("tasks", payload.get("data", []))
    if not isinstance(tasks, list):
        raise ValueError("Label Studio payload must be a list of tasks")

    records: list[AnnotationRecord] = []
    for idx, task in enumerate(tasks):
        data = task.get("data", {})
        text = data.get(text_key) or data.get("text") or ""
        item_id = str(task.get("id", f"item_{idx}"))
        article_id = str(task.get("meta", {}).get("article_id", item_id))

        sentiment: SentimentAnnotation | None = None
        spans: list[EntitySpan] = []
        events: list[EventAnnotation] = []

        annotations = task.get("annotations") or task.get("completions") or []
        for anno in annotations:
            for result in anno.get("result", []) or []:
                from_name = result.get("from_name", "")
                if from_name == "sentiment":
                    choices = result.get("value", {}).get("choices") or []
                    if choices and choices[0] in {s.value for s in SentimentLabel}:
                        sentiment = SentimentAnnotation(label=SentimentLabel(choices[0]))
                elif from_name in ("ner", "money"):
                    span = _ls_span_from_result(result, text)
                    if span is not None and from_name == "ner":
                        spans.append(span)
                elif from_name == "event_type":
                    choices = result.get("value", {}).get("choices") or []
                    for choice in choices:
                        if choice in {e.value for e in EventType}:
                            evidence = _ls_span_from_result(
                                {"value": result.get("value", {})}, text
                            )
                            events.append(
                                EventAnnotation(
                                    event_type=EventType(choice), evidence_span=evidence
                                )
                            )

        records.append(
            AnnotationRecord(
                item_id=item_id,
                article_id=article_id,
                split=str(task.get("meta", {}).get("split", split)),
                text=text,
                sentiment=sentiment,
                spans=spans,
                events=events,
            )
        )
    return records


# --------------------------------------------------------------------------
# Doccano import
# --------------------------------------------------------------------------

def doccano_to_records(
    lines: Iterable[str] | str,
    *,
    split: str = "train",
) -> list[AnnotationRecord]:
    """Convert Doccano JSONL export text into ``AnnotationRecord`` objects."""
    if isinstance(lines, str):
        raw_lines = lines.splitlines()
    else:
        raw_lines = list(lines)

    records: list[AnnotationRecord] = []
    for idx, line in enumerate(raw_lines):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        text = obj.get("text", "")
        item_id = str(obj.get("id", f"item_{idx}"))
        article_id = str(obj.get("meta", {}).get("article_id", item_id))

        spans: list[EntitySpan] = []
        for label in obj.get("labels", []) or []:
            start = label[0]
            end = label[1]
            etype = label[2]
            if etype not in {t.value for t in EntityType}:
                continue
            spans.append(
                EntitySpan(
                    start=int(start),
                    end=int(end),
                    text=text[int(start) : int(end)],
                    entity_type=EntityType(etype),
                )
            )

        sentiment: SentimentAnnotation | None = None
        categories = obj.get("category") or obj.get("categories")
        if isinstance(categories, str) and categories in {s.value for s in SentimentLabel}:
            sentiment = SentimentAnnotation(label=SentimentLabel(categories))
        elif isinstance(categories, list) and categories:
            first = categories[0]
            if first in {s.value for s in SentimentLabel}:
                sentiment = SentimentAnnotation(label=SentimentLabel(first))

        records.append(
            AnnotationRecord(
                item_id=item_id,
                article_id=article_id,
                split=str(obj.get("meta", {}).get("split", split)),
                text=text,
                sentiment=sentiment,
                spans=spans,
            )
        )
    return records


# --------------------------------------------------------------------------
# Training-ready exports
# --------------------------------------------------------------------------

ExportTask = Literal["sentiment", "token", "events", "entity_sentiment"]


def to_sentiment_jsonl(records: Iterable[AnnotationRecord]) -> Iterator[dict[str, Any]]:
    """Document sentiment classification rows."""
    for record in records:
        if record.sentiment is None or record.sentiment.task != TASK_SENTIMENT:
            continue
        yield {
            "task": TASK_SENTIMENT,
            "item_id": record.item_id,
            "text": record.text,
            "label": getattr(record.sentiment.label, "value", record.sentiment.label),
        }


def to_token_jsonl(records: Iterable[AnnotationRecord]) -> Iterator[dict[str, Any]]:
    """Token classification (BIO) rows for NER."""
    for record in records:
        tokens, tags = spans_to_bio(record.text, record.spans)
        yield {
            "task": TASK_NER,
            "item_id": record.item_id,
            "text": record.text,
            "tokens": tokens,
            "tags": tags,
        }


def to_event_jsonl(records: Iterable[AnnotationRecord]) -> Iterator[dict[str, Any]]:
    """Event classification rows (one row per event with its evidence)."""
    for record in records:
        for event in record.events:
            evidence = event.evidence_span
            yield {
                "task": TASK_EVENTS,
                "item_id": record.item_id,
                "text": record.text,
                "event_type": getattr(event.event_type, "value", event.event_type),
                "evidence": evidence.text if evidence is not None else None,
                "evidence_start": evidence.start if evidence is not None else None,
                "evidence_end": evidence.end if evidence is not None else None,
            }


def to_entity_sentiment_jsonl(
    records: Iterable[AnnotationRecord],
) -> Iterator[dict[str, Any]]:
    """Entity sentiment rows (one row per entity-targeted sentiment)."""
    for record in records:
        sent = record.sentiment
        if sent is None or sent.task != TASK_ENTITY_SENTIMENT:
            continue
        yield {
            "task": TASK_ENTITY_SENTIMENT,
            "item_id": record.item_id,
            "text": record.text,
            "target_entity": sent.target_entity,
            "label": getattr(sent.label, "value", sent.label),
            "rationale": sent.rationale_span.text if sent.rationale_span else None,
        }


_EXPORTERS = {
    "sentiment": to_sentiment_jsonl,
    "token": to_token_jsonl,
    "events": to_event_jsonl,
    "entity_sentiment": to_entity_sentiment_jsonl,
}


def write_training_jsonl(
    records: Iterable[AnnotationRecord],
    path: str | Path,
    *,
    task: ExportTask,
) -> int:
    """Write training-ready JSONL for ``task``; return the row count."""
    if task not in _EXPORTERS:
        raise ValueError(f"unknown task: {task!r}")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as fh:
        for row in _EXPORTERS[task](records):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


# Re-exported for convenience; MoneyAnnotation is validated in validate.py.
__all__ = [
    "bio_to_spans",
    "doccano_to_records",
    "label_studio_to_records",
    "spans_to_bio",
    "tokenize_with_offsets",
    "to_entity_sentiment_jsonl",
    "to_event_jsonl",
    "to_sentiment_jsonl",
    "to_token_jsonl",
    "write_training_jsonl",
    "MoneyAnnotation",
]
