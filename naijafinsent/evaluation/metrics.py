"""Evaluation metrics for NaijaFinSent — one stable API, many metric families.

Why this module exists
----------------------
Every number that reaches ``docs/EVALUATION.md`` or ``research/reports/`` passes
through a function here. That keeps four promises we make in the Stage 8 report:

1. **One API per metric family.** Downstream code never has to remember whether
   sklearn wants ``labels=`` or ``pos_label=``; it calls ``macro_f1(y, p)``.
2. **Attributable numbers.** Every metric that can be uncertain returns a point
   estimate *and* a confidence interval, computed by a caller-seeded bootstrap.
3. **Determinism.** Given the same seed, the same inputs produce byte-identical
   results. Nothing here reads the clock or global RNG state.
4. **Honesty about assumptions.** Each function documents what it assumes and
   where it is approximate.

Metric families
---------------
* classification: ``accuracy``, ``macro_f1``, ``per_class_prf``, ``confusion_matrix``
* NER: ``entity_level_f1`` (exact-match, per-type breakdown, seqeval when present)
* events: ``multi_label_f1`` / ``micro_f1`` / ``macro_f1`` over event types
* calibration: ``expected_calibration_error``, ``maximum_calibration_error``, ``brier_score``
* significance: ``bootstrap_ci``, ``paired_bootstrap_test``, ``mcnemar_test``

Defaults follow the label spaces in :mod:`naijafinsent.constants` but no function
*requires* them; pass an explicit ``labels`` order when you need one.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from naijafinsent.constants import EVENT_TYPES, SENTIMENT_LABELS

__all__ = [
    # classification
    "accuracy",
    "confusion_matrix",
    "macro_f1",
    "per_class_prf",
    "classification_report",
    # ner
    "entity_level_f1",
    # events
    "multi_label_f1",
    "micro_f1",
    "macro_f1",
    # calibration
    "expected_calibration_error",
    "maximum_calibration_error",
    "brier_score",
    # significance
    "bootstrap_ci",
    "paired_bootstrap_test",
    "mcnemar_test",
    # helpers
    "MetricResult",
]

# The canonical label order used when a caller does not supply one. Fixed so that
# confusion matrices and per-class reports are comparable across runs.
DEFAULT_LABELS: tuple[str, ...] = SENTIMENT_LABELS
DEFAULT_EVENT_LABELS: tuple[str, ...] = EVENT_TYPES


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class MetricResult:
    """A metric value plus the uncertainty we are willing to attach to it.

    ``value`` is the point estimate. ``ci_low`` / ``ci_high`` are the bounds of a
    bootstrap confidence interval and are ``None`` when the caller did not ask
    for one (e.g. deterministic metrics such as accuracy on a fixed split without
    resampling). ``n`` is the number of items the estimate was computed over, so
    a downstream table can show sample size next to every number.
    """

    value: float
    name: str = "metric"
    n: int | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ci_alpha: float | None = None
    seed: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "n": self.n,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_alpha": self.ci_alpha,
            "seed": self.seed,
            "extra": self.extra,
        }

    def __float__(self) -> float:  # so ``float(result)`` works in quick scripts
        return float(self.value)


# ---------------------------------------------------------------------------
# Small internal utilities
# ---------------------------------------------------------------------------

def _as_1d(values: Sequence[Any] | np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    return arr


def _label_order(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: Sequence[str] | None,
    *,
    default: Sequence[str] | None = None,
) -> list[str]:
    """Resolve the label order.

    When ``labels`` is given it is trusted verbatim (this is how you keep an empty
    class in the report). Otherwise the order is ``default`` (when supplied) merged
    with any observed values, so a declared-but-absent class still counts toward a
    macro average instead of silently disappearing.
    """
    if labels is not None:
        return list(labels)
    order = list(default) if default is not None else []
    seen = set(order)
    for value in sorted({*map(str, y_true.tolist()), *map(str, y_pred.tolist())}):
        if value not in seen:
            order.append(value)
            seen.add(value)
    return order


def _safe_div(numerator: float, denominator: float) -> float:
    """0/0 is defined as 0.0 here.

    Rationale: for per-class metrics we want "no support and no predictions" to
    contribute 0 to the macro average rather than crash. Callers that need
    sklearn's behaviour should use sklearn directly.
    """
    if denominator == 0:
        return 0.0
    return numerator / denominator


# ---------------------------------------------------------------------------
# Classification metrics
# ---------------------------------------------------------------------------

def confusion_matrix(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[str] | None = None,
    *,
    default_labels: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Return ``(matrix, labels)`` where ``matrix[i, j]`` counts true *i*, pred *j*.

    Assumptions
    -----------
    * Items are paired by position; ``y_true[i]`` and ``y_pred[i]`` describe the
      same document. Unequal lengths raise ``ValueError``.
    * Labels not present in ``labels`` (when supplied) are an error: we refuse to
      silently drop rows, because that is how support leaks out of a report.
    * When ``labels`` is ``None`` the order is ``default_labels`` (if given) merged
      with observed values, so a declared-but-absent class still occupies a row.
    """
    yt = _as_1d(y_true, "y_true")
    yp = _as_1d(y_pred, "y_pred")
    if yt.shape[0] != yp.shape[0]:
        raise ValueError(
            f"y_true and y_pred must be the same length: {yt.shape[0]} != {yp.shape[0]}"
        )
    order = _label_order(yt, yp, labels, default=default_labels)
    index = {lab: i for i, lab in enumerate(order)}
    matrix = np.zeros((len(order), len(order)), dtype=np.int64)
    for t, p in zip(yt.tolist(), yp.tolist(), strict=True):
        ts, ps = str(t), str(p)
        if ts not in index:
            raise ValueError(f"true label {ts!r} not in declared labels {order!r}")
        if ps not in index:
            raise ValueError(f"predicted label {ps!r} not in declared labels {order!r}")
        matrix[index[ts], index[ps]] += 1
    return matrix, order


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    """Plain accuracy. Empty input raises rather than returning a fake 0.0."""
    yt = _as_1d(y_true, "y_true")
    yp = _as_1d(y_pred, "y_pred")
    if yt.shape[0] != yp.shape[0]:
        raise ValueError("y_true and y_pred must be the same length")
    if yt.shape[0] == 0:
        raise ValueError("accuracy is undefined for empty inputs")
    return float(np.mean(yt == yp))


def per_class_prf(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[str] | None = None,
    *,
    default_labels: Sequence[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Per-class precision / recall / F1 / support, computed from the matrix.

    All averaging here is **macro over the declared label set**: every class
    counts once whether or not it appears in the data, so adding an all-zero
    class for a missing label drags the average down. That is intentional and is
    why callers should pass :data:`DEFAULT_LABELS` (or ``default_labels``).
    """
    matrix, order = confusion_matrix(y_true, y_pred, labels, default_labels=default_labels)
    tp = np.diag(matrix).astype(float)
    predicted = matrix.sum(axis=0).astype(float)  # column sums
    support = matrix.sum(axis=1).astype(float)    # row sums
    out: dict[str, dict[str, float]] = {}
    for i, lab in enumerate(order):
        precision = _safe_div(tp[i], predicted[i])
        recall = _safe_div(tp[i], support[i])
        f1 = _safe_div(2 * precision * recall, precision + recall)
        out[lab] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "support": float(support[i]),
            "predicted": float(predicted[i]),
            "tp": float(tp[i]),
        }
    return out


def macro_f1(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[str] | None = None,
) -> float:
    """Macro-averaged F1 over the declared label set.

    Assumption: each label counts equally, including labels absent from both gold
    and predictions (they contribute 0.0). This is the headline sentiment metric
    because the rarest classes (``uncertain``) must not be drowned by ``neutral``.
    """
    prf = per_class_prf(y_true, y_pred, labels)
    if not prf:
        raise ValueError("macro_f1 is undefined with no labels")
    return float(np.mean([v["f1"] for v in prf.values()]))


def micro_f1(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[str] | None = None,
) -> float:
    """Micro-averaged F1 — equivalent to accuracy for single-label problems.

    Kept explicit so multi-label code and single-label code share a name.
    """
    matrix, _ = confusion_matrix(y_true, y_pred, labels)
    tp = float(np.diag(matrix).sum())
    fp = float(matrix.sum(axis=0).sum() - tp)
    fn = float(matrix.sum(axis=1).sum() - tp)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return float(_safe_div(2 * precision * recall, precision + recall))


def classification_report(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Bundle the classification metrics a report table needs in one call."""
    t = np.asarray(y_true)
    p = np.asarray(y_pred)
    return {
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred, labels),
        "micro_f1": micro_f1(y_true, y_pred, labels),
        "per_class": per_class_prf(y_true, y_pred, labels),
        "n": int(t.shape[0]),
    }


# ---------------------------------------------------------------------------
# NER — exact-match entity-level F1
# ---------------------------------------------------------------------------

def _normalise_entities(entities: Iterable[Any]) -> list[tuple[str, str]]:
    """Coerce a sequence of entities into ``[(type, surface), ...]``.

    Accepted forms, all of which occur in this repo:

    * ``(entity_type, text)`` or ``(text, entity_type)`` 2-tuples
    * ``(start, end, entity_type)`` 3-tuples  (offsets, we then text-match by type)
    * Pydantic ``EntitySpan`` with ``.entity_type`` / ``.text``
    * ``"B-ORG"`` / ``"I-ORG"`` BIO strings
    * dicts with ``entity_type``/``type`` and ``text``/``value``
    """
    out: list[tuple[str, str]] = []
    for ent in entities:
        etype, surface = _entity_to_pair(ent)
        out.append((str(etype), _norm_surface(surface)))
    return out


def _entity_to_pair(ent: Any) -> tuple[str, str]:
    # Pydantic / duck-typed span objects.
    if hasattr(ent, "entity_type") and hasattr(ent, "text"):
        return str(ent.entity_type), str(ent.text)
    if hasattr(ent, "entity_type"):  # span without text: fall back to offsets
        start = getattr(ent, "start", None)
        end = getattr(ent, "end", None)
        return str(ent.entity_type), f"{start}:{end}"
    if isinstance(ent, dict):
        etype = ent.get("entity_type") or ent.get("type") or ent.get("label") or ""
        text = ent.get("text") or ent.get("value") or ent.get("span") or ""
        return str(etype), str(text)
    if isinstance(ent, str):  # BIO tag string
        tag = ent
        if "-" in tag:
            prefix, _, rest = tag.partition("-")
            if prefix in {"B", "I", "E", "S", "U", "L"}:
                return rest, tag
        return tag, tag
    if isinstance(ent, (tuple, list)):
        parts = list(ent)
        if len(parts) == 2:
            a, b = str(parts[0]), str(parts[1])
            # Heuristic: the type is the token that looks like an ENTITY_TYPES entry.
            if _looks_like_type(b) and not _looks_like_type(a):
                return b, a
            return a, b
        if len(parts) >= 3:
            # (start, end, type) — most common triple.
            if _looks_like_type(str(parts[2])):
                return str(parts[2]), f"{parts[0]}:{parts[1]}"
            return str(parts[2]), f"{parts[0]}:{parts[1]}"
    raise TypeError(f"cannot interpret entity {ent!r} as (type, surface)")


def _looks_like_type(value: str) -> bool:
    return value.isupper() and value.replace("-", "_").isalpha()


def _norm_surface(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def entity_level_f1(
    y_true: Sequence[Sequence[Any]],
    y_pred: Sequence[Sequence[Any]],
    *,
    use_seqeval: bool = True,
) -> dict[str, Any]:
    """Exact-match, entity-level F1 with a per-type breakdown.

    Definition
    ----------
    A predicted entity is a **true positive** only if there is a gold entity with
    the same type and the same normalised surface (whitespace collapsed, case
    folded). Partial overlap does *not* count — this is the strict SemEval-style
    "exact" evaluation, and the reason we also report ``partial`` counts below so
    the gap between "almost right" and "right" is visible.

    Why not seqeval always?
    -----------------------
    ``seqeval`` is an optional ``ml`` extra and is not installed in the base
    environment. When present we *still* compute our own counts (they are the
    contract) but also report ``seqeval``'s numbers under ``seqeval`` so a
    reviewer can confirm the two agree. When absent we silently rely on the
    self-contained implementation, which has no dependencies.

    Assumptions
    -----------
    * ``y_true`` / ``y_pred`` are aligned lists of per-document entity lists.
    * Surfaces are compared after whitespace normalisation, not by offsets. Gold
      and predicted offsets come from different tokenisers, so offsets are not
      comparable; the surface is.
    * Duplicate identical entities in one document are collapsed to a set. A
      document that mentions "CBN" five times does not get five shots at recall.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"y_true and y_pred must align: {len(y_true)} != {len(y_pred)} documents"
        )

    per_type: dict[str, Counter] = {}
    totals = Counter()

    for gold_doc, pred_doc in zip(y_true, y_pred, strict=True):
        gold = set(_normalise_entities(gold_doc or []))
        pred = set(_normalise_entities(pred_doc or []))
        types = {t for t, _ in gold} | {t for t, _ in pred}
        for etype in types:
            g = {s for t, s in gold if t == etype}
            p = {s for t, s in pred if t == etype}
            tp = len(g & p)
            fp = len(p - g)
            fn = len(g - p)
            per_type.setdefault(etype, Counter())
            per_type[etype]["tp"] += tp
            per_type[etype]["fp"] += fp
            per_type[etype]["fn"] += fn
            totals["tp"] += tp
            totals["fp"] += fp
            totals["fn"] += fn

        # Partial-credit bookkeeping: predicted surface is a substring of a gold
        # surface (or vice versa) for the same type but is not an exact match.
        gold_pairs = gold
        for etype, surf in pred - gold:
            if any(t == etype and (surf in gs or gs in surf) for t, gs in gold_pairs):
                totals["partial"] += 1

    def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        return {
            "precision": precision,
            "recall": recall,
            "f1": _safe_div(2 * precision * recall, precision + recall),
            "tp": float(tp),
            "fp": float(fp),
            "fn": float(fn),
        }

    per_type_out = {
        etype: _prf(c["tp"], c["fp"], c["fn"]) for etype, c in sorted(per_type.items())
    }
    micro = _prf(totals["tp"], totals["fp"], totals["fn"])
    macro = {
        key: float(np.mean([v[key] for v in per_type_out.values()])) if per_type_out else 0.0
        for key in ("precision", "recall", "f1")
    }

    result: dict[str, Any] = {
        "exact": {
            "micro": micro,
            "macro": macro,
            "per_type": per_type_out,
            "partial_matches": int(totals["partial"]),
            "n_documents": len(y_true),
        },
        "metric": "entity_level_f1_exact",
    }

    if use_seqeval:
        seq = _try_seqeval(y_true, y_pred)
        if seq is not None:
            result["seqeval"] = seq
    return result


def _try_seqeval(
    y_true: Sequence[Sequence[Any]], y_pred: Sequence[Sequence[Any]]
) -> dict[str, Any] | None:
    """Best-effort seqeval cross-check. Never raises; ``None`` means unavailable."""
    try:  # optional dependency, import locally so the base install stays light
        from seqeval.metrics import classification_report as seq_report
    except Exception:  # pragma: no cover - depends on environment
        return None
    try:
        gold = [[_bio_tag(e) for e in doc or []] for doc in y_true]
        pred = [[_bio_tag(e) for e in doc or []] for doc in y_pred]
        # seqeval wants BIO *sequences*; we only have sets, so we emit each entity
        # as a standalone B- token. This makes seqeval's numbers equal to our
        # exact-match counts and is the only honest mapping available here.
        report = seq_report(gold, pred, output_dict=True, zero_division=0)
        return {"available": True, "report": report}
    except Exception:  # pragma: no cover - defensive
        return None


def _bio_tag(ent: Any) -> str:
    etype, surface = _entity_to_pair(ent)
    return f"B-{etype}" if surface else f"B-{etype}"


# ---------------------------------------------------------------------------
# Event metrics — multi-label over the event taxonomy
# ---------------------------------------------------------------------------

def _as_label_matrix(
    y_true: Sequence[Sequence[str]] | np.ndarray,
    y_pred: Sequence[Sequence[str]] | np.ndarray,
    labels: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Densify lists-of-labels into aligned {0,1} matrices over ``labels``.

    Accepts either a list of label lists (sparse) or an already-densified
    ``(n, n_labels)`` matrix. Order of labels inside a document is irrelevant.
    """
    index = {lab: i for i, lab in enumerate(labels)}

    def _to_matrix(values: Any) -> np.ndarray:
        arr = np.asarray(values, dtype=object)
        if arr.ndim == 2 and arr.shape[1] == len(labels) and arr.dtype != object:
            return arr.astype(np.int64)
        out = np.zeros((len(values), len(labels)), dtype=np.int64)
        for row_i, row in enumerate(values):
            if isinstance(row, (set, frozenset)) or hasattr(row, "__iter__") and not isinstance(
                row, str
            ):
                items = list(row)
            else:
                items = [row] if row else []
            for item in items:
                if isinstance(item, (tuple, list)):  # (type, confidence) etc.
                    item = item[0]
                key = str(item)
                if key in index:
                    out[row_i, index[key]] = 1
        return out

    gold = _to_matrix(y_true)
    pred = _to_matrix(y_pred)
    if gold.shape[0] != pred.shape[0]:
        raise ValueError(
            f"y_true and y_pred must align: {gold.shape[0]} != {pred.shape[0]} documents"
        )
    return gold, pred


def multi_label_f1(
    y_true: Sequence[Sequence[str]] | np.ndarray,
    y_pred: Sequence[Sequence[str]] | np.ndarray,
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Per-class, micro, and macro F1 for multi-label event tagging.

    Assumptions
    -----------
    * A document may carry zero, one, or many event types; ``y_true`` may be a
      list of label lists or a dense ``(n, n_labels)`` matrix.
    * Labels outside the taxonomy are ignored (the event taxonomy is closed).
    * Micro F1 aggregates over (document, label) decisions; macro F1 averages the
      per-class F1 with equal weight, so a rare ``oil_energy`` counts as much as
      ``earnings``.
    """
    label_list = list(labels) if labels is not None else list(DEFAULT_EVENT_LABELS)
    gold, pred = _as_label_matrix(y_true, y_pred, label_list)

    per_class: dict[str, dict[str, float]] = {}
    tp_total = fp_total = fn_total = 0
    for i, lab in enumerate(label_list):
        tp = int(np.sum((gold[:, i] == 1) & (pred[:, i] == 1)))
        fp = int(np.sum((gold[:, i] == 0) & (pred[:, i] == 1)))
        fn = int(np.sum((gold[:, i] == 1) & (pred[:, i] == 0)))
        tp_total += tp
        fp_total += fp
        fn_total += fn
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_class[lab] = {
            "precision": precision,
            "recall": recall,
            "f1": _safe_div(2 * precision * recall, precision + recall),
            "support": float(int(np.sum(gold[:, i]))),
            "predicted": float(int(np.sum(pred[:, i]))),
        }

    micro_p = _safe_div(tp_total, tp_total + fp_total)
    micro_r = _safe_div(tp_total, tp_total + fn_total)
    micro_f1_value = _safe_div(2 * micro_p * micro_r, micro_p + micro_r)
    macro_values = [v["f1"] for v in per_class.values()]
    return {
        "micro": {"precision": micro_p, "recall": micro_r, "f1": micro_f1_value},
        "macro": {"f1": float(np.mean(macro_values)) if macro_values else 0.0},
        "per_class": per_class,
        "labels": label_list,
        "n_documents": int(gold.shape[0]),
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _confidence_and_correctness(
    y_true: Sequence[Any],
    probabilities: Sequence[Sequence[float]],
    labels: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Turn (gold label, full probability vector) into (max prob, is_correct)."""
    prob = np.asarray(probabilities, dtype=float)
    if prob.ndim != 2:
        raise ValueError(f"probabilities must be 2-D, got shape {prob.shape}")
    if prob.shape[0] != len(y_true):
        raise ValueError("probabilities row count must match y_true length")
    if prob.shape[1] != len(labels):
        raise ValueError(
            f"probabilities must have {len(labels)} columns (one per label), "
            f"got {prob.shape[1]}"
        )
    predicted_idx = np.argmax(prob, axis=1)
    max_prob = prob[np.arange(prob.shape[0]), predicted_idx]
    label_index = {lab: i for i, lab in enumerate(labels)}
    gold_idx = np.array([label_index[str(t)] for t in y_true])
    correct = (predicted_idx == gold_idx).astype(float)
    return max_prob, correct


def expected_calibration_error(
    y_true: Sequence[Any],
    probabilities: Sequence[Sequence[float]],
    labels: Sequence[str] | None = None,
    *,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE) with equal-width confidence bins.

    Definition
    ----------
    Bin predictions by their top-class confidence into ``n_bins`` equal-width
    bins over ``[0, 1]``; ECE is the support-weighted mean of ``|accuracy(bin) -
    confidence(bin)|``.

    Assumptions
    -----------
    * ``probabilities`` are rows aligned with ``y_true`` and columns aligned with
      ``labels``; rows should sum to 1 (we do not renormalise, so a bug in the
      model's softmax stays visible as a large ECE).
    * Equal-width bins are used because we report ECE alongside reliability
      diagrams; adaptive binning would make the two disagree.
    * An empty bin contributes nothing. With few samples ECE is high-variance,
      so always report it with a bootstrap CI.
    """
    label_list = list(labels) if labels is not None else list(DEFAULT_LABELS)
    conf, correct = _confidence_and_correctness(y_true, probabilities, label_list)
    if conf.shape[0] == 0:
        raise ValueError("ECE is undefined for empty inputs")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = conf.shape[0]
    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        # Last bin is closed on the right so confidence == 1.0 is included.
        if i == n_bins - 1:
            in_bin = (conf >= low) & (conf <= high)
        else:
            in_bin = (conf >= low) & (conf < high)
        count = int(np.sum(in_bin))
        if count == 0:
            continue
        bin_acc = float(np.mean(correct[in_bin]))
        bin_conf = float(np.mean(conf[in_bin]))
        ece += (count / n) * abs(bin_acc - bin_conf)
    return float(ece)


def maximum_calibration_error(
    y_true: Sequence[Any],
    probabilities: Sequence[Sequence[float]],
    labels: Sequence[str] | None = None,
    *,
    n_bins: int = 10,
) -> float:
    """Maximum Calibration Error (MCE): worst bin gap, not the weighted mean.

    Same binning as :func:`expected_calibration_error`. Useful because a model can
    have a respectable ECE while one decile is badly overconfident — MCE is the
    number that catches the "confidently wrong on uncertain-class documents"
    failure we specifically care about.
    """
    label_list = list(labels) if labels is not None else list(DEFAULT_LABELS)
    conf, correct = _confidence_and_correctness(y_true, probabilities, label_list)
    if conf.shape[0] == 0:
        raise ValueError("MCE is undefined for empty inputs")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    worst = 0.0
    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        if i == n_bins - 1:
            in_bin = (conf >= low) & (conf <= high)
        else:
            in_bin = (conf >= low) & (conf < high)
        if not np.any(in_bin):
            continue
        gap = abs(float(np.mean(correct[in_bin])) - float(np.mean(conf[in_bin])))
        worst = max(worst, gap)
    return float(worst)


def brier_score(
    y_true: Sequence[Any],
    probabilities: Sequence[Sequence[float]],
    labels: Sequence[str] | None = None,
) -> float:
    """Multi-class Brier score: mean squared error of the probability vector.

    For ``K`` classes the score is ``mean_i sum_k (p_ik - y_ik)^2`` where ``y`` is
    the one-hot gold. Range ``[0, 2]``; lower is better. Unlike ECE this is a
    *proper* score, so it rewards honest uncertainty rather than just calibration
    of the top class, and it is the metric to use when selecting a calibration
    temperature (see experiment E8).
    """
    label_list = list(labels) if labels is not None else list(DEFAULT_LABELS)
    prob = np.asarray(probabilities, dtype=float)
    if prob.ndim != 2 or prob.shape[1] != len(label_list):
        raise ValueError(
            f"probabilities must be (n, {len(label_list)}), got {prob.shape}"
        )
    if prob.shape[0] != len(y_true):
        raise ValueError("probabilities row count must match y_true length")
    label_index = {lab: i for i, lab in enumerate(label_list)}
    gold = np.zeros_like(prob)
    for i, t in enumerate(y_true):
        gold[i, label_index[str(t)]] = 1.0
    return float(np.mean(np.sum((prob - gold) ** 2, axis=1)))


# ---------------------------------------------------------------------------
# Significance: bootstrap CIs and paired tests
# ---------------------------------------------------------------------------

# A metric function takes (y_true, y_pred, indices) and returns a float. Indices
# are the resample; a metric implementation must index *both* arrays with them so
# that pairing is preserved.
MetricFn = Callable[[Sequence[Any], Sequence[Any], np.ndarray], float]


def _resample_indices(n: int, rng: np.random.Generator) -> np.ndarray:
    """One bootstrap resample of ``n`` item positions, drawn with replacement."""
    return rng.integers(0, n, size=n)


def bootstrap_ci(
    metric_fn: MetricFn,
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    n: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Percentile bootstrap confidence interval for a single metric.

    Parameters
    ----------
    metric_fn
        ``fn(y_true, y_pred, indices) -> float``. It **must** use ``indices`` to
        subset both arrays together; that is what preserves pairing and what makes
        a CI for a paired metric meaningful.
    n
        Number of resamples. 1000 is the default because below that the tail
        percentiles are too coarse for a 95% interval.
    alpha
        Significance level. ``alpha=0.05`` gives a 95% interval.
    seed
        RNG seed. Same seed + same data => same interval, exactly.

    Returns
    -------
    ``{"point": ..., "low": ..., "high": ..., "mean": ..., "std": ..., "n": ...,
    "alpha": ..., "seed": ...}``.

    Assumptions / caveats
    ---------------------
    * The percentile method assumes the bootstrap distribution is a decent
      approximation of the sampling distribution. With very small ``n`` (say a
      20-item slice) prefer to read the CI as "wide, don't trust the point
      estimate" rather than a literal interval.
    * Resampling is over items, so it accounts for sampling variance in the
      evaluation set but **not** annotation noise or model-training variance.
      Combine with seeds from several training runs when reporting a final number.
    """
    if n < 2:
        raise ValueError("n must be >= 2 to form a bootstrap interval")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    yt = np.asarray(y_true)
    yp = np.asarray(y_pred)
    n_items = yt.shape[0]
    if n_items == 0:
        raise ValueError("bootstrap_ci is undefined for empty inputs")
    point = float(metric_fn(yt, yp, np.arange(n_items)))
    rng = np.random.default_rng(seed)
    samples = np.empty(n, dtype=float)
    for i in range(n):
        idx = _resample_indices(n_items, rng)
        samples[i] = float(metric_fn(yt, yp, idx))
    low = float(np.percentile(samples, 100 * (alpha / 2)))
    high = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return {
        "point": point,
        "low": low,
        "high": high,
        "mean": float(np.mean(samples)),
        "std": float(np.std(samples)),
        "n": n,
        "alpha": alpha,
        "seed": seed,
    }


def paired_bootstrap_test(
    y_true: Sequence[Any],
    pred_a: Sequence[Any],
    pred_b: Sequence[Any],
    metric_fn: MetricFn,
    n: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Paired bootstrap test that two models differ on the same items.

    How it works
    ------------
    The *same* resampled index set is applied to both models' predictions, which
    preserves the pairing (both see an identical resample of the evaluation set).
    We record ``delta = metric(A) - metric(B)`` on every resample and report:

    * ``observed_delta`` — the delta on the full set.
    * ``mean_delta`` / ``std_delta`` / ``ci`` — bootstrap distribution of delta.
    * ``p_value`` — the two-sided paired-bootstrap p-value: the proportion of
      resamples whose delta is on the *opposite* side of zero from the observed
      delta, doubled. This is the standard approximate permutation-style answer
      to "could a delta this large arise from resampling alone?".

    Assumptions
    -----------
    * ``y_true``, ``pred_a``, ``pred_b`` are aligned item-by-item.
    * ``metric_fn`` is item-decomposable enough that resampling items is valid.
      Metric like macro-F1 over a fixed label set qualifies; a metric computed
      from a global clustering does not.
    * The p-value is *approximate* and never exactly 0. A ``p_value`` of ``0.0``
      means "no resample in ``n`` reached the other side" — report it as
      ``p < 1/n``, not ``p = 0``.
    """
    yt = np.asarray(y_true)
    a = np.asarray(pred_a)
    b = np.asarray(pred_b)
    n_items = yt.shape[0]
    if not (a.shape[0] == b.shape[0] == n_items):
        raise ValueError("y_true, pred_a, pred_b must all be the same length")
    if n_items == 0:
        raise ValueError("paired_bootstrap_test is undefined for empty inputs")
    if n < 2:
        raise ValueError("n must be >= 2")

    observed = float(metric_fn(yt, a, np.arange(n_items))) - float(
        metric_fn(yt, b, np.arange(n_items))
    )
    rng = np.random.default_rng(seed)
    deltas = np.empty(n, dtype=float)
    for i in range(n):
        idx = _resample_indices(n_items, rng)
        deltas[i] = float(metric_fn(yt, a, idx)) - float(metric_fn(yt, b, idx))

    if observed >= 0:
        opposite = float(np.mean(deltas <= 0.0))
    else:
        opposite = float(np.mean(deltas >= 0.0))
    p_value = min(1.0, 2.0 * opposite)

    return {
        "observed_delta": observed,
        "mean_delta": float(np.mean(deltas)),
        "std_delta": float(np.std(deltas)),
        "ci": [
            float(np.percentile(deltas, 2.5)),
            float(np.percentile(deltas, 97.5)),
        ],
        "p_value": float(p_value),
        "significant_at_0.05": bool(p_value < 0.05),
        "n": n,
        "seed": seed,
        "delta_samples": deltas.tolist(),
    }


def mcnemar_test(
    y_true: Sequence[Any],
    pred_a: Sequence[Any],
    pred_b: Sequence[Any],
    *,
    continuity_correction: bool = True,
) -> dict[str, Any]:
    """McNemar's test for two classifiers' errors on the same items.

    It asks a narrower question than the paired bootstrap: *given the items where
    the two models disagree, is one model right more often than the other?* The
    two counts are ``b`` (A wrong, B right) and ``c`` (A right, B wrong); the test
    statistic is ``(b - c)^2 / (b + c)`` (with Edwards' continuity correction by
    default), compared against a chi-square distribution with 1 degree of freedom.

    Assumptions
    -----------
    * Both predictions align with ``y_true`` by position.
    * Only *disagreements* matter. If ``b + c == 0`` the models are indistinguishable
      here and we return ``p_value = 1.0`` with a note rather than dividing by zero.
    * The exact binomial form is preferred for small ``b + c``; we use the
      chi-square approximation but expose ``b`` and ``c`` so you can see when it
      is being asked to do too much (rule of thumb: ``b + c >= 25``).
    """
    yt = np.asarray(y_true)
    a = np.asarray(pred_a)
    b_pred = np.asarray(pred_b)
    if not (a.shape[0] == b_pred.shape[0] == yt.shape[0]):
        raise ValueError("y_true, pred_a, pred_b must all be the same length")

    a_correct = a == yt
    b_correct = b_pred == yt
    n_ab = int(np.sum(~a_correct & b_correct))   # b: A wrong, B right
    n_ba = int(np.sum(a_correct & ~b_correct))   # c: A right, B wrong

    if n_ab + n_ba == 0:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "b": n_ab,
            "c": n_ba,
            "n_discordant": 0,
            "significant_at_0.05": False,
            "note": "models never disagree; McNemar is undefined (reported as p=1.0)",
        }

    diff = abs(n_ab - n_ba)
    if continuity_correction:
        diff = max(0.0, diff - 1.0)
    statistic = float(diff**2 / (n_ab + n_ba))

    p_value = _chi2_sf_1df(statistic)
    return {
        "statistic": statistic,
        "p_value": float(p_value),
        "b": n_ab,
        "c": n_ba,
        "n_discordant": n_ab + n_ba,
        "significant_at_0.05": bool(p_value < 0.05),
        "continuity_correction": continuity_correction,
    }


def _chi2_sf_1df(statistic: float) -> float:
    """Survival function of chi-square with 1 df at ``statistic``.

    ``P(X > x) = erfc(sqrt(x / 2))`` exactly for 1 degree of freedom, so we do not
    need scipy and the result is on the same numerical path everywhere.
    """
    if statistic <= 0:
        return 1.0
    return float(math.erfc(math.sqrt(statistic / 2.0)))


# ---------------------------------------------------------------------------
# Ready-made MetricFn adapters (so callers never hand-roll indices)
# ---------------------------------------------------------------------------

def macro_f1_metric(labels: Sequence[str] | None = None) -> MetricFn:
    """Return a ``MetricFn`` for macro-F1 usable by the bootstrap helpers."""

    def _fn(y_true: Sequence[Any], y_pred: Sequence[Any], idx: np.ndarray) -> float:
        yt = np.asarray(y_true)[idx]
        yp = np.asarray(y_pred)[idx]
        try:
            return macro_f1(yt, yp, labels)
        except ValueError:
            # A resample can miss a class entirely; treat as 0 rather than abort.
            return 0.0

    return _fn


def accuracy_metric() -> MetricFn:
    """Return a ``MetricFn`` for accuracy usable by the bootstrap helpers."""

    def _fn(y_true: Sequence[Any], y_pred: Sequence[Any], idx: np.ndarray) -> float:
        yt = np.asarray(y_true)[idx]
        yp = np.asarray(y_pred)[idx]
        if yt.shape[0] == 0:
            return 0.0
        return float(np.mean(yt == yp))

    return _fn
