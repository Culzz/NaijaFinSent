"""Active learning: uncertainty sampling and learning-curve bookkeeping.

Stage 3 experiment E7 compares active labelling against random labelling. This
module supplies the ranking strategies, deterministic batch selection, and a
``learning_curve`` structure to record (batch index, training size, metric)
points for both arms.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Strategy = Literal["least_confidence", "margin", "entropy"]


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def _normalise(probs: Mapping[str, float]) -> dict[str, float]:
    total = sum(probs.values())
    if total <= 0:
        n = len(probs) or 1
        return dict.fromkeys(probs, 1.0 / n)
    return {k: v / total for k, v in probs.items()}


def uncertainty_score(probs: Mapping[str, float], strategy: Strategy) -> float:
    """Return an uncertainty score; higher means more uncertain.

    * ``least_confidence`` — ``1 - max(p)``.
    * ``margin``           — ``1 - (p_top1 - p_top2)`` (small margin = uncertain).
    * ``entropy``          — normalised Shannon entropy in ``[0, 1]``.
    """
    if not probs:
        return 0.0
    p = _normalise(probs)
    values = sorted(p.values(), reverse=True)

    if strategy == "least_confidence":
        return 1.0 - values[0]
    if strategy == "margin":
        top2 = values[1] if len(values) > 1 else 0.0
        return 1.0 - (values[0] - top2)
    if strategy == "entropy":
        h = -sum(v * math.log(v) for v in p.values() if v > 0)
        h_max = math.log(len(p)) if len(p) > 1 else 1.0
        return h / h_max if h_max > 0 else 0.0
    raise ValueError(f"unknown strategy: {strategy!r}")


def rank_by_uncertainty(
    probabilities: Mapping[str, Mapping[str, float]],
    *,
    strategy: Strategy = "entropy",
) -> list[tuple[str, float]]:
    """Rank ``{item_id: {label: prob}}`` by uncertainty, most uncertain first.

    Ties break on item_id ascending so the ranking is deterministic.
    """
    scored = [(item_id, uncertainty_score(probs, strategy)) for item_id, probs in probabilities.items()]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored


# --------------------------------------------------------------------------
# Batch selection
# --------------------------------------------------------------------------

def select_batch(
    probabilities: Mapping[str, Mapping[str, float]],
    *,
    batch_size: int,
    strategy: Strategy = "entropy",
    already_labelled: Sequence[str] = (),
) -> list[str]:
    """Select the next batch of ``batch_size`` item ids (deterministic)."""
    if batch_size <= 0:
        return []
    excluded = set(already_labelled)
    ranked = rank_by_uncertainty(
        {k: v for k, v in probabilities.items() if k not in excluded},
        strategy=strategy,
    )
    return [item_id for item_id, _score in ranked[:batch_size]]


def select_random_batch(
    item_ids: Sequence[str],
    *,
    batch_size: int,
    seed: int = 42,
    already_labelled: Sequence[str] = (),
) -> list[str]:
    """Random-arm batch selection for the E7 comparison (same seeding scheme)."""
    import random

    rng = random.Random(seed)
    pool = sorted(set(item_ids) - set(already_labelled))
    rng.shuffle(pool)
    return pool[:batch_size]


# --------------------------------------------------------------------------
# Learning curve
# --------------------------------------------------------------------------

@dataclass
class LearningCurvePoint:
    """One point on a learning curve."""

    batch_index: int
    training_size: int
    metric: float
    metric_name: str = "f1"
    strategy: str = "entropy"


@dataclass
class LearningCurve:
    """A single labelling arm's curve (active or random)."""

    arm: str
    seed: int
    metric_name: str = "f1"
    points: list[LearningCurvePoint] = field(default_factory=list)

    def add(self, batch_index: int, training_size: int, metric: float) -> None:
        self.points.append(
            LearningCurvePoint(
                batch_index=batch_index,
                training_size=training_size,
                metric=metric,
                metric_name=self.metric_name,
                strategy=self.arm,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "seed": self.seed,
            "metric_name": self.metric_name,
            "points": [
                {
                    "batch_index": p.batch_index,
                    "training_size": p.training_size,
                    "metric": p.metric,
                }
                for p in self.points
            ],
        }


def compare_curves(active: LearningCurve, random_arm: LearningCurve) -> dict[str, Any]:
    """Summarise the E7 active-vs-random comparison.

    Reports the metric at each shared training size and the area under the curve
    (trapezoidal, on the min shared support) for both arms.
    """
    active_by_size = {p.training_size: p.metric for p in active.points}
    random_by_size = {p.training_size: p.metric for p in random_arm.points}
    shared = sorted(set(active_by_size) & set(random_by_size))

    def _auc(curve_by_size: Mapping[int, float], sizes: Sequence[int]) -> float:
        if len(sizes) < 2:
            return curve_by_size[sizes[0]] if sizes else 0.0
        area = 0.0
        for i in range(1, len(sizes)):
            x0, x1 = sizes[i - 1], sizes[i]
            area += (curve_by_size[x0] + curve_by_size[x1]) / 2 * (x1 - x0)
        return area / (sizes[-1] - sizes[0])

    return {
        "n_shared_points": len(shared),
        "shared_training_sizes": shared,
        "auc_active": _auc(active_by_size, shared),
        "auc_random": _auc(random_by_size, shared),
        "auc_gain": _auc(active_by_size, shared) - _auc(random_by_size, shared),
        "active": active.to_dict(),
        "random": random_arm.to_dict(),
    }


def write_learning_curves(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write a learning-curve comparison to JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return out
