"""Record validation: the rules stated in ``docs/ANNOTATION_GUIDE.md``.

``validate_record`` returns a list of human-readable problem strings (empty =
valid). ``validate_dataset`` aggregates problems by rule id. Both are pure and
dependency-free so they can run at import time in any tool.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from naijafinsent.annotation.guidelines import VALIDATION_CONSTANTS
from naijafinsent.constants import ENTITY_TYPES, EVENT_TYPES, SENTIMENT_LABELS
from naijafinsent.schemas import (
    AnnotationRecord,
    EventAnnotation,
    MoneyAnnotation,
    SentimentAnnotation,
)

# Rule ids, so reports can be grouped and unit tests can assert on them.
RULE_SPAN_BOUNDS = "span_out_of_bounds"
RULE_SPAN_TEXT = "span_text_mismatch"
RULE_SPAN_OVERLAP = "span_overlap_cross_type"
RULE_SPAN_LENGTH = "span_length"
RULE_ENTITY_TYPE = "entity_type_not_allowed"
RULE_EVENT_TYPE = "event_type_not_allowed"
RULE_SENTIMENT_LABEL = "sentiment_label_not_allowed"
RULE_SENTIMENT_TARGET = "sentiment_target_inconsistent"
RULE_MONEY_UNIT = "money_unit_inferred"
RULE_MONEY_CURRENCY = "money_currency_not_allowed"
RULE_EVENT_EVIDENCE = "event_evidence_missing"
RULE_EVENT_DATE = "event_date_rule"
RULE_DUPLICATE_SPAN = "duplicate_span"
RULE_RECORD_LIMITS = "record_limits"

_ALLOWED_CURRENCIES = frozenset(VALIDATION_CONSTANTS["allowed_currencies"])
_ALLOWED_UNITS = frozenset(VALIDATION_CONSTANTS["allowed_units"])
_MAX_SPAN_CHARS = int(VALIDATION_CONSTANTS["max_span_chars"])
_MIN_SPAN_CHARS = int(VALIDATION_CONSTANTS["min_span_chars"])
_MAX_SPANS = int(VALIDATION_CONSTANTS["max_spans_per_record"])
_MAX_EVENTS = int(VALIDATION_CONSTANTS["max_events_per_record"])


def _problem(rule: str, message: str) -> str:
    return f"[{rule}] {message}"


# --------------------------------------------------------------------------
# Span helpers
# --------------------------------------------------------------------------

def _check_span_bounds(span, text: str, where: str) -> list[str]:
    problems: list[str] = []
    n = len(text)
    if span.start < 0 or span.end > n:
        problems.append(
            _problem(
                RULE_SPAN_BOUNDS,
                f"{where}: offsets [{span.start}:{span.end}] outside text bounds [0:{n}]",
            )
        )
    return problems


def _check_span_text(span, text: str, where: str) -> list[str]:
    problems: list[str] = []
    n = len(text)
    if span.start < 0 or span.end > n or span.start >= span.end:
        # bounds already reported; text check is meaningless
        return problems
    actual = text[span.start : span.end]
    if actual != span.text:
        problems.append(
            _problem(
                RULE_SPAN_TEXT,
                f"{where}: text[{span.start}:{span.end}] is {actual!r}, span.text is {span.text!r}",
            )
        )
    return problems


def _check_span_length(span, where: str) -> list[str]:
    length = len(span.text)
    if length < _MIN_SPAN_CHARS or length > _MAX_SPAN_CHARS:
        return [
            _problem(
                RULE_SPAN_LENGTH,
                f"{where}: span length {length} outside [{_MIN_SPAN_CHARS},{_MAX_SPAN_CHARS}]",
            )
        ]
    return []


def _check_entity_type(span, where: str) -> list[str]:
    value = getattr(span.entity_type, "value", span.entity_type)
    if value not in ENTITY_TYPES:
        return [_problem(RULE_ENTITY_TYPE, f"{where}: entity_type {value!r} not in allowed set")]
    return []


# --------------------------------------------------------------------------
# Cross-span overlap check
# --------------------------------------------------------------------------

def _interval_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _check_overlaps(record: AnnotationRecord) -> list[str]:
    """Spans of *different types* must never overlap.

    Identical (start, end, type) triples collapse to one; identical offsets with
    different types are a cross-type overlap and are reported.
    """
    problems: list[str] = []
    # Collect typed spans from across the record with provenance labels.
    typed: list[tuple[str, int, int, str]] = []
    for i, span in enumerate(record.spans):
        typed.append((f"spans[{i}]", span.start, span.end, str(getattr(span.entity_type, "value", span.entity_type))))
    for i, money in enumerate(record.money):
        s = money.span
        typed.append((f"money[{i}].span", s.start, s.end, str(getattr(s.entity_type, "value", s.entity_type))))
    for i, event in enumerate(record.events):
        if event.evidence_span is not None:
            s = event.evidence_span
            typed.append(
                (
                    f"events[{i}].evidence_span",
                    s.start,
                    s.end,
                    str(getattr(s.entity_type, "value", s.entity_type)),
                )
            )

    seen_triples: set[tuple[int, int, str]] = set()
    for where, start, end, etype in typed:
        triple = (start, end, etype)
        if triple in seen_triples:
            problems.append(
                _problem(RULE_DUPLICATE_SPAN, f"{where}: duplicate span ({start}:{end}, {etype})")
            )
        seen_triples.add(triple)

    for i in range(len(typed)):
        for j in range(i + 1, len(typed)):
            w_i, s_i, e_i, t_i = typed[i]
            w_j, s_j, e_j, t_j = typed[j]
            if t_i == t_j:
                continue
            if _interval_overlap(s_i, e_i, s_j, e_j):
                problems.append(
                    _problem(
                        RULE_SPAN_OVERLAP,
                        f"{w_i} ({t_i} {s_i}:{e_i}) overlaps {w_j} ({t_j} {s_j}:{e_j})",
                    )
                )
    return problems


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------

def _check_money(money: MoneyAnnotation, text: str, where: str) -> list[str]:
    problems: list[str] = []
    problems += _check_span_bounds(money.span, text, where)
    problems += _check_span_text(money.span, text, where)
    problems += _check_span_length(money.span, where)
    problems += _check_entity_type(money.span, where)

    if money.currency is not None and money.currency not in _ALLOWED_CURRENCIES:
        problems.append(
            _problem(
                RULE_MONEY_CURRENCY,
                f"{where}: currency {money.currency!r} not in {sorted(_ALLOWED_CURRENCIES)}",
            )
        )
    if money.unit is not None and money.unit not in _ALLOWED_UNITS:
        problems.append(
            _problem(RULE_MONEY_UNIT, f"{where}: unit {money.unit!r} not in allowed units")
        )
    # Never infer a missing unit: if the span has no scale word but carries a
    # unit, the unit was invented. Detect common scale words in the span text.
    if money.unit is not None:
        lowered = money.span.text.lower()
        unit = money.unit.lower()
        stated = (
            unit in lowered
            or (unit == "million" and ("m" in lowered and "$" in lowered or "million" in lowered))
            or (unit == "billion" and ("bn" in lowered or "billion" in lowered))
            or (unit == "trillion" and ("tn" in lowered or "trillion" in lowered))
            or (unit == "thousand" and ("k" in lowered or "thousand" in lowered))
            or unit == "kobo"
        )
        if not stated:
            problems.append(
                _problem(
                    RULE_MONEY_UNIT,
                    f"{where}: unit {money.unit!r} not stated in span {money.span.text!r} "
                    "(guide rule: never infer a missing unit)",
                )
            )
    return problems


# --------------------------------------------------------------------------
# Sentiment
# --------------------------------------------------------------------------

def _check_sentiment(sent: SentimentAnnotation, text: str) -> list[str]:
    problems: list[str] = []
    label = getattr(sent.label, "value", sent.label)
    if label not in SENTIMENT_LABELS:
        problems.append(
            _problem(RULE_SENTIMENT_LABEL, f"sentiment.label {label!r} not in allowed set")
        )
    if sent.task == "entity_sentiment" and VALIDATION_CONSTANTS["entity_sentiment_requires_target"]:
        if not sent.target_entity:
            problems.append(
                _problem(
                    RULE_SENTIMENT_TARGET,
                    "sentiment.task == 'entity_sentiment' but target_entity is missing",
                )
            )
    if sent.task == "sentiment" and sent.target_entity:
        problems.append(
            _problem(
                RULE_SENTIMENT_TARGET,
                "sentiment.task == 'sentiment' (document) must not carry target_entity",
            )
        )
    if sent.rationale_span is not None:
        problems += _check_span_bounds(sent.rationale_span, text, "sentiment.rationale_span")
        problems += _check_span_text(sent.rationale_span, text, "sentiment.rationale_span")
    return problems


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def _check_event(event: EventAnnotation, text: str, where: str) -> list[str]:
    problems: list[str] = []
    etype = getattr(event.event_type, "value", event.event_type)
    if etype not in EVENT_TYPES:
        problems.append(
            _problem(RULE_EVENT_TYPE, f"{where}: event_type {etype!r} not in allowed set")
        )
    if VALIDATION_CONSTANTS["require_event_evidence"] and event.evidence_span is None:
        problems.append(_problem(RULE_EVENT_EVIDENCE, f"{where}: evidence_span is required"))
    if event.evidence_span is not None:
        problems += _check_span_bounds(event.evidence_span, text, f"{where}.evidence_span")
        problems += _check_span_text(event.evidence_span, text, f"{where}.evidence_span")
    for j, ent in enumerate(event.entities):
        problems += _check_span_bounds(ent, text, f"{where}.entities[{j}]")
        problems += _check_span_text(ent, text, f"{where}.entities[{j}]")
        problems += _check_entity_type(ent, f"{where}.entities[{j}]")
    return problems


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def validate_record(record: AnnotationRecord) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    text = record.text

    if not record.item_id:
        problems.append(_problem(RULE_RECORD_LIMITS, "item_id is empty"))
    if not record.article_id:
        problems.append(_problem(RULE_RECORD_LIMITS, "article_id is empty"))

    if len(record.spans) > _MAX_SPANS:
        problems.append(
            _problem(RULE_RECORD_LIMITS, f"{len(record.spans)} spans > max {_MAX_SPANS}")
        )
    if len(record.events) > _MAX_EVENTS:
        problems.append(
            _problem(RULE_RECORD_LIMITS, f"{len(record.events)} events > max {_MAX_EVENTS}")
        )

    for i, span in enumerate(record.spans):
        where = f"spans[{i}]"
        problems += _check_span_bounds(span, text, where)
        problems += _check_span_text(span, text, where)
        problems += _check_span_length(span, where)
        problems += _check_entity_type(span, where)

    for i, money in enumerate(record.money):
        problems += _check_money(money, text, f"money[{i}]")

    for i, event in enumerate(record.events):
        problems += _check_event(event, text, f"events[{i}]")

    if record.sentiment is not None:
        problems += _check_sentiment(record.sentiment, text)

    problems += _check_overlaps(record)
    return problems


def validate_dataset(records: Iterable[AnnotationRecord]) -> dict:
    """Validate many records and summarise error counts by rule id."""
    records = list(records)
    rule_counts: Counter[str] = Counter()
    invalid_records = 0
    examples: dict[str, list[str]] = {}

    for record in records:
        problems = validate_record(record)
        if not problems:
            continue
        invalid_records += 1
        for problem in problems:
            rule = problem.split("]", 1)[0].lstrip("[")
            rule_counts[rule] += 1
            examples.setdefault(rule, [])
            if len(examples[rule]) < 3:
                examples[rule].append(f"{record.item_id}: {problem}")

    return {
        "n_records": len(records),
        "n_valid": len(records) - invalid_records,
        "n_invalid": invalid_records,
        "n_problems": int(sum(rule_counts.values())),
        "by_rule": dict(rule_counts.most_common()),
        "examples": examples,
    }


def _load_records(path: Path) -> list[AnnotationRecord]:
    records: list[AnnotationRecord] = []
    if path.suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(AnnotationRecord.model_validate(json.loads(line)))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("records", [])
        records = [AnnotationRecord.model_validate(item) for item in payload]
    return records


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: validate a JSON/JSONL file of AnnotationRecords."""
    parser = argparse.ArgumentParser(description="Validate NaijaFinSent annotation records.")
    parser.add_argument("path", type=Path, help="JSON or JSONL file of records")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    records = _load_records(args.path)
    report = validate_dataset(records)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Validated {report['n_records']} records: "
            f"{report['n_valid']} valid, {report['n_invalid']} invalid "
            f"({report['n_problems']} problems)"
        )
        for rule, count in report["by_rule"].items():
            print(f"  {rule}: {count}")
            for example in report["examples"].get(rule, []):
                print(f"    - {example}")

    return 0 if report["n_invalid"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
