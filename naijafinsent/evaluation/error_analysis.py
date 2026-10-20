"""Structured error analysis: a taxonomy, heuristic tagging, and a manual queue.

Why a taxonomy instead of "here are 100 wrong examples"
-------------------------------------------------------
The Stage 8 requirement is a **100+ error analysis with a taxonomy** and
representative examples, not an anecdote pile. We define the categories the brief
names — sarcasm, mixed sentiment, naira/macro language, Pidgin, unseen entities,
abbreviations — plus a few that the Nigerian financial-news domain forces on us
(code-switching, long documents, annotation ambiguity). Each category has:

* a stable id used in artefacts,
* a one-line definition,
* heuristic rules that can *suggest* the tag, and
* an explicit note that the heuristics are a **triage aid**, not ground truth.

The human still reads the queue. ``manual_queue`` hands a person the highest-value
errors first and stores whatever label they give it, so the final report can state
how many errors each category actually accounts for rather than how many the
regexes thought it did.

Everything is deterministic: given the same inputs the same tags and the same
queue order come out. No random sampling without a seed.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from naijafinsent.evaluation.slices import get_field, length_bucket

__all__ = [
    "ErrorCategory",
    "ERROR_CATEGORIES",
    "CATEGORY_BY_ID",
    "ErrorRecord",
    "categorise_error",
    "tag_errors",
    "manual_queue",
    "error_summary",
    "export_errors_csv",
    "export_errors_jsonl",
    "make_error_records",
]


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorCategory:
    """One node of the error taxonomy.

    ``heuristic_confidence`` records how much to trust automatic tagging for this
    category, which is why the report separates "auto-tagged" counts from
    "human-confirmed" counts.
    """

    id: str
    label: str
    definition: str
    heuristic_confidence: str  # "high" | "medium" | "low"


ERROR_CATEGORIES: tuple[ErrorCategory, ...] = (
    ErrorCategory(
        id="sarcasm",
        label="Sarcasm / irony",
        definition=(
            "Surface-positive wording used to express a negative judgement "
            "(or the reverse), so the literal polarity is inverted."
        ),
        heuristic_confidence="low",
    ),
    ErrorCategory(
        id="mixed_sentiment",
        label="Mixed sentiment",
        definition=(
            "The document contains both clearly positive and clearly negative "
            "statements about the same target, and document-level single-label "
            "annotation forces a choice the text does not make."
        ),
        heuristic_confidence="medium",
    ),
    ErrorCategory(
        id="naira_macro",
        label="Naira / macro language",
        definition=(
            "Polarity depends on macro context (devaluation, MPR, FX windows) "
            "where the same wording means good news for one actor and bad for "
            "another; naive lexical cues flip sign."
        ),
        heuristic_confidence="medium",
    ),
    ErrorCategory(
        id="pidgin",
        label="Pidgin",
        definition=(
            "Nigerian Pidgin expressions whose polarity markers are not in the "
            "model's English vocabulary (e.g. 'e don better', 'wahala don land')."
        ),
        heuristic_confidence="high",
    ),
    ErrorCategory(
        id="unseen_entity",
        label="Unseen entity",
        definition=(
            "The document's target entity never appeared in training, so the "
            "model has no learned association for it (new ticker, new regulator "
            "circular, new company)."
        ),
        heuristic_confidence="low",
    ),
    ErrorCategory(
        id="abbreviation",
        label="Abbreviation / acronym",
        definition=(
            "Domain abbreviations and tickers (MPR, FX, NGN, NPL, CAPEX, DANGCEM) "
            "used without expansion, which tokenisation and pretrained vocabulary "
            "handle unevenly."
        ),
        heuristic_confidence="high",
    ),
    ErrorCategory(
        id="code_switching",
        label="Code-switching",
        definition=(
            "Sentences that mix English, Pidgin, and/or a Nigerian language, "
            "often within one clause."
        ),
        heuristic_confidence="medium",
    ),
    ErrorCategory(
        id="annotation_ambiguity",
        label="Annotation ambiguity",
        definition=(
            "The gold label itself is contestable (guideline gap, borderline "
            "'uncertain' vs 'neutral'); a disagreement here may be a guideline "
            "problem, not a model problem."
        ),
        heuristic_confidence="low",
    ),
    ErrorCategory(
        id="long_document",
        label="Long document / truncation",
        definition=(
            "The decisive sentence sits outside the model's input window, or is "
            "diluted by boilerplate, so the document-level label is unreachable "
            "from the truncated text."
        ),
        heuristic_confidence="medium",
    ),
    ErrorCategory(
        id="uncertain_neutral_confusion",
        label="Uncertain vs neutral confusion",
        definition=(
            "The model collapses the 'uncertain' (doubt/conditional) class into "
            "'neutral' (no position). This is a known hard boundary in our schema."
        ),
        heuristic_confidence="high",
    ),
)

CATEGORY_BY_ID: dict[str, ErrorCategory] = {c.id: c for c in ERROR_CATEGORIES}


# ---------------------------------------------------------------------------
# Heuristic rules
# ---------------------------------------------------------------------------

# Kept as explicit tables, not inline regex soup, so reviewers can audit and the
# tests can point at the exact pattern they rely on.

_PIDGIN_MARKERS: tuple[str, ...] = (
    "wahala", "dey", "don land", "e don", "no be", "sabi", "abeg", "chop",
    "gbege", "oga", "wetin", "yansh", "palava", "shey", "na so", "make we",
    "carry go", "go slow", "kudi",
)

_SARCASM_MARKERS: tuple[str, ...] = (
    "yeah right", "sure thing", "as if", "of course!", "wonderful news",
    "brilliant idea", "what a surprise", "\"stable\"", "so-called", "again?!",
)

_MACRO_TERMS: tuple[str, ...] = (
    "mpr", "monetary policy rate", "devaluation", "devalue", "fx window",
    "foreign exchange", "naira", "exchange rate", "inflation", "subsidy",
    "interest rate", "bps", "basis points", "imf", "dollar shortage",
)

_POSITIVE_CUES: tuple[str, ...] = (
    "profit", "growth", "surge", "rally", "gain", "strong", "record high",
    "beat", "upgrade", "dividend", "expanded", "improved", "rose", "jumped",
)

_NEGATIVE_CUES: tuple[str, ...] = (
    "loss", "decline", "slump", "fall", "weak", "miss", "downgrade", "fine",
    "sanction", "fraud", "plunge", "fell", "dropped", "crisis", "default",
)

_ABBREVIATION_RE = re.compile(r"\b(?:[A-Z]{2,6})\b")

_UNCERTAIN_MARKERS: tuple[str, ...] = (
    "may", "might", "could", "expected to", "if ", "subject to", "pending",
    "unclear", "possibly", "likely to", "would ",
)


@dataclass
class ErrorRecord:
    """One analysed error, carrying both gold/pred and any discovered tags."""

    item_id: str
    text: str
    gold: Any
    pred: Any
    tags: list[str] = field(default_factory=list)
    confirmed_tags: list[str] = field(default_factory=list)
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def categorise_error(
    sample: Any,
    gold: Any,
    pred: Any,
    rules: dict[str, Any] | None = None,
) -> list[str]:
    """Heuristically tag one misprediction with taxonomy category ids.

    Returns a list of ids (possibly empty) in a fixed taxonomy order, so results
    are deterministic. The heuristics are deliberately transparent — each rule
    below is a simple, auditable check, and the returned tags are *candidates*
    for a human to confirm in :func:`manual_queue`.

    Parameters
    ----------
    sample
        A sample object/dict. Used for the text and, when available, the
        ``seen_entities`` / ``train_entities`` metadata for the unseen-entity
        rule.
    gold, pred
        The gold and predicted labels. Compared as strings.
    rules
        Optional override table with keys ``pidgin``, ``sarcasm``, ``macro``,
        ``positive``, ``negative``, ``uncertain``, ``abbreviations``. Any missing
        key falls back to the built-in table. Exposing this is how tests pin the
        behaviour without depending on the exact word lists.

    Assumptions
    -----------
    * ``text`` is the *document* text the model saw. If the model was fed a
      truncated string, pass that string so the long-document rule fires.
    * The unseen-entity rule can only fire when the sample exposes which entities
      were unseen; otherwise it never fires (we never guess).
    """
    table = _merge_rules(rules)
    text = str(get_field(sample, "text", "content", "title", default="") or "")
    lowered = text.casefold()
    tags: list[str] = []

    gold_s, pred_s = str(gold), str(pred)

    # Pidgin — lexical markers are a strong signal.
    if _contains_any(lowered, table["pidgin"]):
        tags.append("pidgin")

    # Code-switching — Pidgin markers alongside clear English financial verbs.
    if "pidgin" in tags and _contains_any(lowered, table["macro"]):
        tags.append("code_switching")

    # Abbreviations / tickers.
    caps = _ABBREVIATION_RE.findall(text)
    if len(caps) >= 2 or _contains_any(lowered, table["abbreviations"]):
        tags.append("abbreviation")

    # Naira / macro language.
    if _contains_any(lowered, table["macro"]):
        tags.append("naira_macro")

    # Sarcasm — quotation marks around a positive cue, or an explicit marker.
    if _contains_any(lowered, table["sarcasm"]) or _quoted_positive(text, table["positive"]):
        tags.append("sarcasm")

    # Mixed sentiment — strong cues of both polarity in the same document.
    has_pos = _contains_any(lowered, table["positive"])
    has_neg = _contains_any(lowered, table["negative"])
    if has_pos and has_neg:
        tags.append("mixed_sentiment")

    # Uncertain vs neutral boundary.
    if {gold_s, pred_s} == {"uncertain", "neutral"}:
        tags.append("uncertain_neutral_confusion")
    elif _contains_any(lowered, table["uncertain"]) and "uncertain" in {gold_s, pred_s}:
        tags.append("uncertain_neutral_confusion")

    # Long document / truncation.
    if len(text) > 3000:
        tags.append("long_document")

    # Unseen entity — only when the sample tells us.
    unseen = get_field(sample, "unseen_entities", "unseen_entity", default=None)
    if unseen:
        tags.append("unseen_entity")

    # Annotation ambiguity — the two labels sit on a contested boundary and the
    # text fires mixed cues, i.e. the gold itself is arguably wrong.
    if "mixed_sentiment" in tags and {gold_s, pred_s} <= {"positive", "negative", "neutral"}:
        tags.append("annotation_ambiguity")

    # Emit in taxonomy order, de-duplicated.
    order = {c.id: i for i, c in enumerate(ERROR_CATEGORIES)}
    return sorted(set(tags), key=lambda t: order.get(t, len(order)))


def _merge_rules(rules: dict[str, Any] | None) -> dict[tuple[str, ...], Any]:
    base: dict[str, tuple[str, ...]] = {
        "pidgin": _PIDGIN_MARKERS,
        "sarcasm": _SARCASM_MARKERS,
        "macro": _MACRO_TERMS,
        "positive": _POSITIVE_CUES,
        "negative": _NEGATIVE_CUES,
        "uncertain": _UNCERTAIN_MARKERS,
        "abbreviations": ("ngn", "mpr", "fx", "npl", "capex", "eps", "roe"),
    }
    if rules:
        for key in list(base):
            if rules.get(key):
                base[key] = tuple(rules[key])
    return base


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


def _quoted_positive(text: str, positives: Iterable[str]) -> bool:
    """Detect a positive cue wrapped in scare quotes, a common sarcasm tell."""
    for cue in positives:
        for pattern in (f'"{cue}', f"'{cue}", f"“{cue}"):
            if pattern in text.casefold():
                return True
    return False


# ---------------------------------------------------------------------------
# Tag collection, manual queue, summary
# ---------------------------------------------------------------------------

def tag_errors(
    errors: Sequence[ErrorRecord],
    rules: dict[str, Any] | None = None,
) -> list[ErrorRecord]:
    """Fill ``tags`` on each record using :func:`categorise_error`.

    Mutates and returns the same records. ``confirmed_tags`` (set by a human in
    :func:`manual_queue`) is never overwritten.
    """
    for record in errors:
        record.tags = categorise_error(
            {"text": record.text, **record.metadata}, record.gold, record.pred, rules
        )
    return errors


def manual_queue(
    errors: Sequence[ErrorRecord],
    n: int = 100,
    *,
    seed: int = 0,
    prioritise: Sequence[str] | None = None,
) -> list[ErrorRecord]:
    """Return the top ``n`` errors for a human to read, in a deterministic order.

    Ordering is by *triage value*, highest first:

    1. Errors whose highest-confidence auto-tag is ``high`` (a cheap, likely-real
       finding we can confirm quickly).
    2. Errors with more auto-tags (ambiguous in several ways → more informative).
    3. A seeded tie-break, so the queue is reproducible but not alphabetical
       (alphabetical would cluster on one publisher's item ids).

    ``prioritise`` lets a caller force categories to the front (e.g. put
    ``sarcasm`` first for a dedicated read-through). The returned records are the
    *same objects*, so a human's ``confirmed_tags`` edit is visible to the caller.

    The requirement is a 100+ error read; call this with ``n >= 100`` for the
    report and paste the resulting category counts into the taxonomy table.
    """
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    priority_ids = list(prioritise or [])
    priority_index = {cid: i for i, cid in enumerate(priority_ids)}

    def sort_key(indexed: tuple[int, ErrorRecord]) -> tuple[int, int, int, int]:
        index, record = indexed
        if priority_ids:
            matched = [priority_index[t] for t in record.tags if t in priority_index]
            priority = min(matched) if matched else len(priority_ids)
        else:
            priority = 0
        best_conf = min(
            (confidence_rank.get(CATEGORY_BY_ID[t].heuristic_confidence, 3)
             for t in record.tags if t in CATEGORY_BY_ID),
            default=3,
        )
        # Shuffle deterministically by mixing the seed with the position.
        jitter = hash((seed, index)) & 0xFFFF
        return (priority, best_conf, -len(record.tags), jitter)

    ordered = sorted(enumerate(errors), key=sort_key)
    return [record for _, record in ordered[:n]]


def error_summary(tagged_errors: Sequence[ErrorRecord]) -> dict[str, Any]:
    """Count tags across errors and pull representative examples per category.

    Returns::

        {
          "n_errors": int,
          "counts": {category_id: int or {auto, confirmed}},
          "by_category": {category_id: {...definition..., "auto": n,
                                       "confirmed": m, "examples": [...]}},
          "untagged": int,
        }

    ``examples`` are up to three records per category (deterministic: the first
    three in input order), each trimmed to a readable snippet. ``untagged`` counts
    errors no rule fired on — that number is itself a finding: it is the size of
    the "we do not know why this failed" bucket that the manual read must shrink.
    """
    counts: Counter[str] = Counter()
    confirmed: Counter[str] = Counter()
    untagged = 0
    for record in tagged_errors:
        if not record.tags:
            untagged += 1
        for tag in record.tags:
            counts[tag] += 1
        for tag in record.confirmed_tags:
            confirmed[tag] += 1

    by_category: dict[str, Any] = {}
    for cat in ERROR_CATEGORIES:
        examples = [
            {
                "item_id": r.item_id,
                "gold": str(r.gold),
                "pred": str(r.pred),
                "snippet": _snippet(r.text),
                "tags": list(r.tags),
            }
            for r in tagged_errors
            if cat.id in r.tags
        ][:3]
        by_category[cat.id] = {
            "label": cat.label,
            "definition": cat.definition,
            "heuristic_confidence": cat.heuristic_confidence,
            "auto": int(counts.get(cat.id, 0)),
            "confirmed": int(confirmed.get(cat.id, 0)),
            "examples": examples,
        }

    return {
        "n_errors": len(tagged_errors),
        "counts": {cat.id: int(counts.get(cat.id, 0)) for cat in ERROR_CATEGORIES},
        "confirmed_counts": {
            cat.id: int(confirmed.get(cat.id, 0)) for cat in ERROR_CATEGORIES
        },
        "by_category": by_category,
        "untagged": untagged,
    }


def _snippet(text: str, limit: int = 240) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_CSV_FIELDS = ("item_id", "gold", "pred", "tags", "confirmed_tags", "snippet", "notes")


def export_errors_csv(errors: Sequence[ErrorRecord], path: str | Path) -> Path:
    """Write errors to a CSV a human can open in a spreadsheet and annotate.

    The ``confirmed_tags`` column is left as whatever the record holds (usually
    empty), so the same file can be filled in by hand and re-read by the report
    builder. Returns the path actually written.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_CSV_FIELDS))
        writer.writeheader()
        for record in errors:
            writer.writerow(
                {
                    "item_id": record.item_id,
                    "gold": record.gold,
                    "pred": record.pred,
                    "tags": "|".join(record.tags),
                    "confirmed_tags": "|".join(record.confirmed_tags),
                    "snippet": _snippet(record.text),
                    "notes": record.notes,
                }
            )
    return out


def export_errors_jsonl(errors: Sequence[ErrorRecord], path: str | Path) -> Path:
    """Write full error records to JSONL (one object per line) for programmatic use.

    Unlike the CSV this keeps the complete text and metadata, so a downstream
    reader (or a future dedup pass) does not need the source corpus.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for record in errors:
            fh.write(json.dumps(record.as_dict(), ensure_ascii=False, default=str) + "\n")
    return out


def make_error_records(
    gold: Sequence[Any],
    pred: Sequence[Any],
    samples: Sequence[Any],
) -> list[ErrorRecord]:
    """Convenience: build :class:`ErrorRecord` objects for every misprediction.

    A record is created wherever ``gold != pred``; correct items are skipped
    because the taxonomy is about failure modes. ``item_id`` falls back to the
    sample's index when the sample carries no id, which keeps records joinable.
    """
    if not (len(gold) == len(pred) == len(samples)):
        raise ValueError("gold, pred and samples must be position-aligned")
    records: list[ErrorRecord] = []
    for i, (g, p, sample) in enumerate(zip(gold, pred, samples, strict=True)):
        if str(g) == str(p):
            continue
        item_id = get_field(sample, "item_id", "id", "article_id", default=str(i))
        records.append(
            ErrorRecord(
                item_id=str(item_id),
                text=str(get_field(sample, "text", "content", "title", default="") or ""),
                gold=g,
                pred=p,
                metadata={"length_bucket": length_bucket(len(str(get_field(
                    sample, "text", "content", default="") or "")))},
            )
        )
    return records
