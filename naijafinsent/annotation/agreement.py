"""Inter-annotator agreement (IQA) and adjudication helpers.

Implements, from first principles and without depending on scikit-learn:

* multi-class **Cohen's kappa** with the standard chance-correction formula;
* **span-level F1** for NER using seqeval-style entity-level matching, with
  exact and partial (overlap) match modes;
* **per-class agreement** (per-label agreement rate and one-vs-rest kappa);
* **majority vote** for adjudication;
* an **agreement report** shaped for ``research/reports/agreement.json``.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from naijafinsent.schemas import AnnotationRecord, EntitySpan, SentimentAnnotation

# --------------------------------------------------------------------------
# Cohen's kappa (multi-class)
# --------------------------------------------------------------------------

def cohens_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """Multi-class Cohen's kappa.

    ``kappa = (p_o - p_e) / (1 - p_e)`` where ``p_o`` is the observed
    agreement and ``p_e`` is the agreement expected by chance, computed from
    the marginals of the pooled label distribution. Returns ``0.0`` when
    ``p_e == 1`` (both annotators used a single, identical label) because
    chance agreement is total and kappa is undefined; returns ``1.0`` for
    perfect agreement on non-degenerate data.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("label sequences must be the same length")
    n = len(labels_a)
    if n == 0:
        return 0.0

    p_o = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n

    counts_a: Counter[str] = Counter(labels_a)
    counts_b: Counter[str] = Counter(labels_b)
    categories = set(counts_a) | set(counts_b)
    p_e = 0.0
    for cat in categories:
        p_e += (counts_a.get(cat, 0) / n) * (counts_b.get(cat, 0) / n)

    if p_e >= 1.0:
        # Both annotators used one category (the same one). Degenerate but
        # perfectly consistent by construction.
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


# --------------------------------------------------------------------------
# Span-level F1 (seqeval-style entity-level matching)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _KeyedSpan:
    start: int
    end: int
    label: str


def _span_key(span: EntitySpan) -> _KeyedSpan:
    return _KeyedSpan(span.start, span.end, str(getattr(span.entity_type, "value", span.entity_type)))


def _matches(a: _KeyedSpan, b: _KeyedSpan, mode: str) -> bool:
    if a.label != b.label:
        return False
    if mode == "exact":
        return a.start == b.start and a.end == b.end
    if mode == "partial":
        return a.start < b.end and b.start < a.end  # any character overlap
    raise ValueError(f"unknown match mode: {mode!r}")


def span_level_f1(
    spans_a: Sequence[EntitySpan],
    spans_b: Sequence[EntitySpan],
    *,
    match: str = "exact",
) -> dict[str, float]:
    """Entity-level precision / recall / F1 between two annotators.

    Greedy one-to-one matching (each predicted span may match at most one gold
    span), which is the seqeval contract. ``match='exact'`` requires identical
    offsets and label; ``match='partial'`` requires the same label and any
    character overlap.
    """
    if match not in ("exact", "partial"):
        raise ValueError(f"unknown match mode: {match!r}")

    gold = [_span_key(s) for s in spans_a]
    pred = [_span_key(s) for s in spans_b]

    matched = 0
    used_gold: set[int] = set()
    for p in pred:
        for gi, g in enumerate(gold):
            if gi in used_gold:
                continue
            if _matches(g, p, match):
                used_gold.add(gi)
                matched += 1
                break

    n_pred = len(pred)
    n_gold = len(gold)
    precision = matched / n_pred if n_pred else 0.0
    recall = matched / n_gold if n_gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": float(matched),
        "n_gold": float(n_gold),
        "n_pred": float(n_pred),
    }


# --------------------------------------------------------------------------
# Per-class agreement
# --------------------------------------------------------------------------

def per_class_agreement(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
) -> dict[str, dict[str, float]]:
    """Per-label raw agreement rate and one-vs-rest kappa."""
    if len(labels_a) != len(labels_b):
        raise ValueError("label sequences must be the same length")

    categories = sorted(set(labels_a) | set(labels_b))
    out: dict[str, dict[str, float]] = {}
    for cat in categories:
        bin_a = [1 if x == cat else 0 for x in labels_a]
        bin_b = [1 if x == cat else 0 for x in labels_b]
        agree = sum(1 for x, y in zip(bin_a, bin_b, strict=True) if x == y)
        rate = agree / len(bin_a) if bin_a else 0.0
        kappa = cohens_kappa([str(v) for v in bin_a], [str(v) for v in bin_b])
        out[cat] = {"agreement": rate, "kappa_ovr": kappa}
    return out


# --------------------------------------------------------------------------
# Adjudication: majority vote
# --------------------------------------------------------------------------

def _sentiment_vote(records: Sequence[AnnotationRecord]) -> SentimentAnnotation | None:
    labels = [
        str(getattr(r.sentiment.label, "value", r.sentiment.label))
        for r in records
        if r.sentiment is not None
    ]
    if not labels:
        return None
    winner = Counter(labels).most_common(1)[0][0]
    # Preserve the task/target of the first matching annotation.
    for r in records:
        if r.sentiment is not None and str(getattr(r.sentiment.label, "value")) == winner:
            return r.sentiment.model_copy(update={"annotator": "majority_vote"})
    return SentimentAnnotation(label=SentimentAnnotation.model_fields["label"].annotation(winner))


def _span_vote(records: Sequence[AnnotationRecord], min_votes: int) -> list[EntitySpan]:
    # Vote on exact (start, end, type) triples.
    votes: dict[tuple[int, int, str], list[EntitySpan]] = defaultdict(list)
    for r in records:
        for s in r.spans:
            key = (s.start, s.end, str(getattr(s.entity_type, "value", s.entity_type)))
            votes[key].append(s)
    kept: list[EntitySpan] = []
    for _key, spans in votes.items():
        if len(spans) >= min_votes:
            kept.append(spans[0])
    kept.sort(key=lambda s: (s.start, s.end))
    return kept


def _event_vote(records: Sequence[AnnotationRecord], min_votes: int):
    votes: dict[str, list[Any]] = defaultdict(list)
    for r in records:
        for e in r.events:
            votes[str(getattr(e.event_type, "value", e.event_type))].append(e)
    kept = []
    for _etype, events in votes.items():
        if len(events) >= min_votes:
            kept.append(events[0])
    return kept


def majority_vote(
    records_by_annotator: Mapping[str, AnnotationRecord] | Sequence[AnnotationRecord],
    *,
    min_votes: int = 2,
) -> AnnotationRecord:
    """Adjudicate several annotators' records for one item into one record.

    Accepts either a mapping ``{annotator: record}`` or a sequence of records.
    Majority thresholds: sentiment takes the modal label; a span or event is
    kept only if at least ``min_votes`` annotators produced it.
    """
    if isinstance(records_by_annotator, Mapping):
        records = list(records_by_annotator.values())
    else:
        records = list(records_by_annotator)
    if not records:
        raise ValueError("no records to adjudicate")

    base = records[0]
    if len(records) == 1:
        return base.model_copy(deep=True)

    sentiment = _sentiment_vote(records)
    spans = _span_vote(records, min_votes)
    events = _event_vote(records, min_votes)

    # Majority money: vote by exact span offsets among money annotations.
    money_votes: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for r in records:
        for m in r.money:
            money_votes[(m.span.start, m.span.end)].append(m)
    money = [vals[0] for vals in money_votes.values() if len(vals) >= min_votes]

    return AnnotationRecord(
        item_id=base.item_id,
        article_id=base.article_id,
        split=base.split,
        text=base.text,
        sentiment=sentiment,
        spans=spans,
        money=money,
        events=events,
    )


# --------------------------------------------------------------------------
# Agreement report
# --------------------------------------------------------------------------

@dataclass
class AnnotatorPair:
    """A double-annotated item's two annotators and their records."""

    item_id: str
    annotator_a: str
    annotator_b: str
    record_a: AnnotationRecord
    record_b: AnnotationRecord
    extra: dict[str, Any] = field(default_factory=dict)


def agreement_report(
    pairs: Iterable[AnnotatorPair],
    *,
    alpha_gate: float = 0.60,
    f1_gate: float = 0.70,
) -> dict[str, Any]:
    """Build a report dict ready to be written to ``research/reports/agreement.json``."""
    pairs = list(pairs)
    sent_a: list[str] = []
    sent_b: list[str] = []
    event_a: list[str] = []
    event_b: list[str] = []
    f1_exact: list[float] = []
    f1_partial: list[float] = []
    per_item: list[dict[str, Any]] = []

    for pair in pairs:
        la = _sentiment_label(pair.record_a)
        lb = _sentiment_label(pair.record_b)
        if la is not None and lb is not None:
            sent_a.append(la)
            sent_b.append(lb)

        ea = sorted(str(getattr(e.event_type, "value", e.event_type)) for e in pair.record_a.events)
        eb = sorted(str(getattr(e.event_type, "value", e.event_type)) for e in pair.record_b.events)
        event_a.extend(ea)
        event_b.extend(eb)

        fe = span_level_f1(pair.record_a.spans, pair.record_b.spans, match="exact")
        fp = span_level_f1(pair.record_a.spans, pair.record_b.spans, match="partial")
        f1_exact.append(fe["f1"])
        f1_partial.append(fp["f1"])
        per_item.append(
            {
                "item_id": pair.item_id,
                "sentiment_a": la,
                "sentiment_b": lb,
                "sentiment_agree": (la == lb) if (la and lb) else None,
                "ner_f1_exact": fe["f1"],
                "ner_f1_partial": fp["f1"],
                "event_agree": ea == eb,
            }
        )

    sentiment_kappa = cohens_kappa(sent_a, sent_b) if sent_a else None
    event_agreement = (
        sum(1 for a, b in zip(event_a, event_b, strict=True) if a == b) / len(event_a)
        if event_a and len(event_a) == len(event_b)
        else None
    )
    mean_f1_exact = sum(f1_exact) / len(f1_exact) if f1_exact else 0.0
    mean_f1_partial = sum(f1_partial) / len(f1_partial) if f1_partial else 0.0

    gates = {
        "sentiment_kappa_pass": (sentiment_kappa is not None and sentiment_kappa >= alpha_gate),
        "ner_f1_pass": mean_f1_exact >= f1_gate,
    }

    return {
        "n_pairs": len(pairs),
        "n_sentiment_items": len(sent_a),
        "sentiment_kappa": sentiment_kappa,
        "sentiment_per_class": per_class_agreement(sent_a, sent_b) if sent_a else {},
        "ner_f1_exact_mean": mean_f1_exact,
        "ner_f1_partial_mean": mean_f1_partial,
        "event_agreement": event_agreement,
        "gates": gates,
        "thresholds": {"kappa_min": alpha_gate, "f1_min": f1_gate},
        "per_item": per_item,
    }


def _sentiment_label(record: AnnotationRecord) -> str | None:
    if record.sentiment is None:
        return None
    return str(getattr(record.sentiment.label, "value", record.sentiment.label))


def write_agreement_report(report: Mapping[str, Any], path: str | Path) -> Path:
    """Write an agreement report to JSON and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(report), indent=2), encoding="utf-8")
    return out
