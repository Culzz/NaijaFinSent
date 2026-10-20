"""Slice-based evaluation: per-publisher, topic, length, and time reporting.

Why slicing matters here
------------------------
A single macro-F1 hides the failures that matter to a reader: the model may be
strong on BusinessDay wire copy and weak on Pidgin-heavy Punch columns, or strong
in 2024 and weak after the 2023 naira float. Stage 8 requires per-slice numbers
**with counts and confidence intervals**, because a slice of 12 documents cannot
support a claim about a publisher.

Design
------
A slice is just a name plus a key function that maps a sample to a bucket label.
Samples are duck-typed: anything with a ``publisher``/``topic``/``published_at``
attribute or a dict with those keys works, and callers can pass their own
``key_fn`` when they need something else.

``slice_report`` returns, per slice, the metric value, the sample count, and a
bootstrap CI — plus an explicit flag when a slice is too small to trust. Nothing
here invents numbers: a slice with zero items is reported with ``count == 0`` and
``metric is None``, never a fake 0.0.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from typing import Any

import numpy as np

from naijafinsent.evaluation.metrics import MetricFn, bootstrap_ci, macro_f1_metric

__all__ = [
    "get_field",
    "publisher_key",
    "topic_key",
    "length_bucket_key",
    "period_key",
    "slice_by",
    "slice_report",
    "drift_curve",
    "length_bucket",
]

# A slice key function maps one sample to a bucket label (or None to drop it).
KeyFn = Callable[[Any], str | None]

# Below this many items a slice is reported but flagged ``low_support``.
MIN_SLICE_SIZE: int = 20

# Length bucket edges in characters of the (already normalised) document text.
LENGTH_BUCKET_EDGES: tuple[tuple[str, int], ...] = (
    ("short:<600", 600),
    ("medium:600-1500", 1500),
    ("long:1500-3000", 3000),
    ("very_long:>3000", 10**9),
)


# ---------------------------------------------------------------------------
# Field access — samples may be dicts or objects
# ---------------------------------------------------------------------------

def get_field(sample: Any, *names: str, default: Any = None) -> Any:
    """Fetch the first present field from a dict-like or attribute-like sample.

    Tries each name in order so callers do not need to know whether the sample
    uses ``published_at`` or ``published``. Returns ``default`` when none match.
    """
    for name in names:
        if isinstance(sample, dict):
            if name in sample:
                return sample[name]
        elif hasattr(sample, name):
            value = getattr(sample, name)
            if value is not None:
                return value
    return default


# ---------------------------------------------------------------------------
# Standard key functions
# ---------------------------------------------------------------------------

def publisher_key(sample: Any) -> str | None:
    """Bucket by publisher/source name, normalised to a lower-case slug."""
    value = get_field(sample, "publisher", "source", "source_id", "publisher_name")
    if value is None:
        return None
    return " ".join(str(value).split()).casefold()


def topic_key(sample: Any) -> str | None:
    """Bucket by topic/sector tag.

    Accepts a string, or a list of tags (we take the first, since a document in
    two topics should be counted once; use an explicit ``key_fn`` when you want
    to explode multi-topic documents instead).
    """
    value = get_field(sample, "topic", "sector", "category", "topics", "tags")
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        value = next(iter(value), None)
    if value is None:
        return None
    return " ".join(str(value).split()).casefold()


def length_bucket(length: int) -> str:
    """Map a character length to one of :data:`LENGTH_BUCKET_EDGES`."""
    for name, upper in LENGTH_BUCKET_EDGES:
        if length < upper:
            return name
    return LENGTH_BUCKET_EDGES[-1][0]


def length_bucket_key(sample: Any, *, field: str = "text") -> str | None:
    """Bucket by document length in characters.

    Uses the ``text`` field by default; pass ``field="content"`` for articles.
    Length is measured on the raw text as given (not tokenised), which is the
    honest choice because the model saw that exact string.
    """
    text = get_field(sample, field, "content", "title")
    if text is None:
        return None
    return length_bucket(len(str(text)))


def period_key(sample: Any, *, granularity: str = "month") -> str | None:
    """Bucket by publication time as ``YYYY`` (yearly) or ``YYYY-MM`` (monthly).

    Assumptions
    -----------
    * ``published_at`` may be a ``datetime``, ``date``, or ISO-ish string. Naive
      datetimes are treated as-is; we do not guess a timezone.
    * Samples with no publish date return ``None`` and are dropped from the slice
      (they cannot be placed on a drift curve).
    """
    value = get_field(sample, "published_at", "published", "publish_date", "date", "created_at")
    if value is None:
        return None
    parsed = _coerce_datetime(value)
    if parsed is None:
        return None
    if granularity == "year":
        return f"{parsed.year:04d}"
    return f"{parsed.year:04d}-{parsed.month:02d}"


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            # Fall back to a leading YYYY-MM or YYYY.
            parts = text[:10].split("-")
            try:
                year = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 else 1
                day = int(parts[2]) if len(parts) > 2 else 1
                return datetime(year, month, day)
            except (ValueError, IndexError):
                return None
    return None


# ---------------------------------------------------------------------------
# Slicing
# ---------------------------------------------------------------------------

def slice_by(
    samples: Sequence[Any],
    key_fn: KeyFn,
    *,
    drop_missing: bool = True,
) -> dict[str, list[int]]:
    """Group sample **indices** by the bucket returned from ``key_fn``.

    Returning indices (not copies of the samples) is deliberate: the caller keeps
    the original arrays and can index ``y_true`` / ``y_pred`` with the same
    positions, which is what keeps gold and predictions aligned.

    ``drop_missing=True`` (default) drops samples whose key is ``None``; set it to
    ``False`` to collect them under ``"__missing__"`` so a report can show how much
    metadata is absent.
    """
    buckets: dict[str, list[int]] = {}
    for i, sample in enumerate(samples):
        key = key_fn(sample)
        if key is None:
            if drop_missing:
                continue
            key = "__missing__"
        buckets.setdefault(str(key), []).append(i)
    # Sort bucket names so iteration order is stable across runs.
    return {k: buckets[k] for k in sorted(buckets)}


def _subset(values: Sequence[Any], index: np.ndarray) -> np.ndarray:
    return np.asarray(values)[index]


def slice_report(
    preds: Sequence[Any],
    gold: Sequence[Any],
    samples: Sequence[Any],
    slice_keys: dict[str, KeyFn] | Sequence[str] | None = None,
    *,
    metric_fn: MetricFn | None = None,
    metric_name: str = "macro_f1",
    labels: Sequence[str] | None = None,
    n_bootstrap: int = 500,
    seed: int = 0,
    min_size: int = MIN_SLICE_SIZE,
) -> dict[str, Any]:
    """Compute per-slice metrics with counts and bootstrap confidence intervals.

    Parameters
    ----------
    preds, gold, samples
        Position-aligned sequences. ``samples`` supplies the metadata for slicing.
    slice_keys
        Either a mapping ``{slice_name: key_fn}`` or a list of built-in names from
        ``{"publisher", "topic", "length", "period"}``. ``None`` runs all four.
    metric_fn
        ``fn(y_true, y_pred, indices) -> float``. Defaults to macro-F1 (with the
        ``labels`` order when supplied) so the primary sentiment metric and the
        report use the same function.
    n_bootstrap
        Resamples per slice CI. Lower than the headline 1000 because this runs
        once per slice per slice dimension; raise it for the final report.
    min_size
        Slices smaller than this get ``"low_support": True``. The metric is still
        reported (hiding it would be worse) but must not be quoted as a finding.

    Returns
    -------
    ``{slice_name: {bucket: {count, metric, ci_low, ci_high, low_support, n}},
    "__meta__": {...}}``. Buckets with zero items never appear; a slice dimension
    that produced no buckets appears with an empty dict and a ``"reason"``.
    """
    if not (len(preds) == len(gold) == len(samples)):
        raise ValueError(
            "preds, gold and samples must be position-aligned: "
            f"{len(preds)}, {len(gold)}, {len(samples)}"
        )

    key_fns = _resolve_slice_keys(slice_keys)
    fn = metric_fn if metric_fn is not None else macro_f1_metric(labels)

    gold_arr = np.asarray(gold)
    pred_arr = np.asarray(preds)

    out: dict[str, Any] = {}
    for slice_name, key_fn in key_fns.items():
        buckets = slice_by(samples, key_fn)
        if not buckets:
            out[slice_name] = {"reason": "no samples carried a usable key"}
            continue
        per_bucket: dict[str, Any] = {}
        for bucket, idx_list in buckets.items():
            idx = np.asarray(idx_list, dtype=int)
            sub_true = gold_arr[idx]
            sub_pred = pred_arr[idx]
            entry: dict[str, Any] = {
                "count": int(len(idx)),
                "low_support": bool(len(idx) < min_size),
            }
            point = float(fn(sub_true, sub_pred, np.arange(len(idx))))
            entry["metric"] = point
            if len(idx) >= 2 and n_bootstrap >= 2:
                ci = bootstrap_ci(
                    fn, sub_true, sub_pred, n=n_bootstrap, seed=seed
                )
                entry["ci_low"] = ci["low"]
                entry["ci_high"] = ci["high"]
                entry["ci_std"] = ci["std"]
            else:
                entry["ci_low"] = None
                entry["ci_high"] = None
                entry["ci_std"] = None
            per_bucket[bucket] = entry
        out[slice_name] = per_bucket

    out["__meta__"] = {
        "metric": metric_name,
        "n_items": int(len(samples)),
        "n_bootstrap": n_bootstrap,
        "seed": seed,
        "min_size": min_size,
        "labels": list(labels) if labels is not None else None,
    }
    return out


def _resolve_slice_keys(
    slice_keys: dict[str, KeyFn] | Sequence[str] | None,
) -> dict[str, KeyFn]:
    builtin: dict[str, KeyFn] = {
        "publisher": publisher_key,
        "topic": topic_key,
        "length": length_bucket_key,
        "period": period_key,
    }
    if slice_keys is None:
        return dict(builtin)
    if isinstance(slice_keys, dict):
        return dict(slice_keys)
    resolved: dict[str, KeyFn] = {}
    for name in slice_keys:
        if name not in builtin:
            raise ValueError(
                f"unknown built-in slice {name!r}; expected one of {sorted(builtin)}"
            )
        resolved[name] = builtin[name]
    return resolved


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def drift_curve(
    samples: Sequence[Any],
    preds: Sequence[Any],
    gold: Sequence[Any],
    period_key_fn: KeyFn,
    metric_fn: MetricFn,
    *,
    n_bootstrap: int = 500,
    seed: int = 0,
    min_size: int = MIN_SLICE_SIZE,
) -> list[dict[str, Any]]:
    """Monthly (or yearly) performance series for experiment E9.

    Returns a list of points sorted by period label, one per period that carries
    at least one item::

        [{"period": "2024-03", "count": 148, "metric": 0.61,
          "ci_low": 0.55, "ci_high": 0.67, "low_support": False}, ...]

    Why a *series* and not a slope
    ------------------------------
    E9 asks whether performance decays over time and whether retraining helps.
    The honest first output is the curve plus its per-period uncertainty; fitting
    a trend line over noisy monthly points would overstate what a few hundred
    documents can support. The consumer (report/plot) can fit afterwards.

    Assumptions
    -----------
    * Period labels are lexicographically sortable (``YYYY`` and ``YYYY-MM`` both
      are), which is true for the labels produced by :func:`period_key`.
    * Periods with a single item are included with ``low_support=True`` and no CI,
      so gaps in the curve are visible rather than silently smoothed away.
    """
    buckets = slice_by(samples, period_key_fn)
    gold_arr = np.asarray(gold)
    pred_arr = np.asarray(preds)

    points: list[dict[str, Any]] = []
    for period in sorted(buckets):
        idx = np.asarray(buckets[period], dtype=int)
        sub_true = gold_arr[idx]
        sub_pred = pred_arr[idx]
        point: dict[str, Any] = {
            "period": period,
            "count": int(len(idx)),
            "low_support": bool(len(idx) < min_size),
        }
        point["metric"] = float(metric_fn(sub_true, sub_pred, np.arange(len(idx))))
        if len(idx) >= 2 and n_bootstrap >= 2:
            ci = bootstrap_ci(metric_fn, sub_true, sub_pred, n=n_bootstrap, seed=seed)
            point["ci_low"] = ci["low"]
            point["ci_high"] = ci["high"]
        else:
            point["ci_low"] = None
            point["ci_high"] = None
        points.append(point)
    return points
