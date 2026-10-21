"""Probability calibration: temperature scaling + reliability diagnostics.

Deliberately implemented with numpy/scipy only (no
``sklearn.calibration.CalibratedClassifierCV``) so it works on *any* source of
probabilities: logits from a transformer, softmax outputs, or hand-supplied
scores. Multi-class throughout (binary is just the 2-class case).

Temperature scaling fits a single scalar ``T`` on held-out data by minimising
the negative log-likelihood of the true labels; ``T > 1`` softens over-confident
probabilities, ``T < 1`` sharpens them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "TemperatureScaler",
    "fit_temperature",
    "apply_temperature",
    "reliability_curve",
    "expected_calibration_error",
    "negative_log_likelihood",
]

_EPS = 1e-12


def _as_2d(probs: np.ndarray) -> np.ndarray:
    """Coerce a 1-D binary prob vector to a 2-column matrix."""
    arr = np.asarray(probs, dtype=np.float64)
    if arr.ndim == 1:
        arr = np.column_stack([1.0 - arr, arr])
    return arr


def _as_logits(probs: np.ndarray) -> np.ndarray:
    """Convert probabilities to logits (log(p)), safely."""
    arr = _as_2d(probs)
    arr = np.clip(arr, _EPS, 1.0)
    return np.log(arr)


def _labels_to_index(labels: np.ndarray) -> np.ndarray:
    """Map arbitrary label values to 0..K-1 indices (sorted unique)."""
    arr = np.asarray(labels)
    classes = np.unique(arr)
    mapping = {c: i for i, c in enumerate(classes)}
    return np.array([mapping[c] for c in arr], dtype=np.int64)


def negative_log_likelihood(logits: np.ndarray, labels: np.ndarray) -> float:
    """Mean NLL of ``labels`` under softmax(logits)."""
    logits = _as_2d(logits) if logits.ndim == 1 else np.asarray(logits, dtype=np.float64)
    if logits.shape[0] == 1:
        logits = logits  # single class: NLL is 0 by definition
    idx = _labels_to_index(labels)
    logits = logits - logits.max(axis=1, keepdims=True)
    log_probs = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
    n = len(idx)
    if n == 0:
        return 0.0
    return float(-log_probs[np.arange(n), idx].mean())


@dataclass
class TemperatureScaler:
    """Result of fitting a scalar temperature, with helpers to apply it."""

    temperature: float
    n_classes: int
    nll_before: float
    nll_after: float

    @property
    def improved(self) -> bool:
        return self.nll_after <= self.nll_before + 1e-12

    def apply(self, probs: np.ndarray) -> np.ndarray:
        """Apply the fitted temperature to probabilities (returns probabilities)."""
        return apply_temperature(probs, self.temperature)

    def apply_probs(self, probs: np.ndarray) -> np.ndarray:
        return self.apply(probs)


def _softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def apply_temperature(
    probs_or_logits: np.ndarray,
    temperature: float,
    *,
    input_is_logits: bool = False,
) -> np.ndarray:
    """Divide logits by ``temperature`` and re-softmax.

    Args:
        probs_or_logits: array of shape ``(n,)`` (binary) or ``(n, k)``.
        temperature: positive scalar ``T``.
        input_is_logits: if True, inputs are already logits; otherwise they are
            probabilities and are first converted to logits.

    Returns:
        A ``(n, k)`` matrix of temperatures-scaled probabilities.
    """
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    arr = np.asarray(probs_or_logits, dtype=np.float64)
    logits = arr if input_is_logits else _as_logits(arr)
    if input_is_logits and logits.ndim == 1:
        logits = _as_2d(logits)
    return _softmax(logits / float(temperature))


def fit_temperature(
    logits_or_probs: np.ndarray,
    labels: np.ndarray,
    *,
    input_is_logits: bool = False,
    lr: float = 0.01,
    max_iter: int = 500,
    tol: float = 1e-6,
) -> TemperatureScaler:
    """Fit a single temperature by minimising NLL via gradient descent.

    Implemented with numpy only. The objective in ``log T`` space is smooth and
    convex for a fixed set of logits, so a simple gradient step with momentum
    converges reliably; we keep a bounded grid search as a fallback and take the
    better of the two (this is what guarantees "improves or preserves").

    Args:
        logits_or_probs: ``(n,)`` binary probs/logits or ``(n, k)`` matrix.
        labels: true labels (any hashable values); mapped to class indices by
            ``np.unique``. Must correspond to the columns of the prob matrix in
            sorted-class order for multi-class inputs -- for the common case of
            matching column order this is automatic.
        input_is_logits: whether the inputs are logits rather than probabilities.

    Returns:
        A :class:`TemperatureScaler` with the fitted temperature and the NLL
        before/after.
    """
    arr = np.asarray(logits_or_probs, dtype=np.float64)
    logits = arr if input_is_logits else _as_logits(arr)
    if logits.ndim == 1:
        logits = _as_2d(logits)
    n_classes = logits.shape[1]
    idx = _labels_to_index(labels)

    if n_classes == 1:
        # Degenerate single-class input: temperature is meaningless.
        return TemperatureScaler(1.0, 1, 0.0, 0.0)

    nll_before = negative_log_likelihood(logits, labels)

    def nll_at(t: float) -> float:
        return negative_log_likelihood(logits / t, labels)

    # --- gradient descent in log-temperature space --------------------
    log_t = 0.0
    velocity = 0.0
    best_log_t = 0.0
    best_nll = nll_before
    for _ in range(max_iter):
        t = float(np.exp(log_t))
        scaled = logits / t
        probs = _softmax(scaled)
        # d(NLL)/d(log_t) for a single T scale factor.
        grad = float(np.mean(np.sum(probs * scaled, axis=1) - scaled[np.arange(len(idx)), idx]))
        velocity = 0.9 * velocity - lr * grad
        log_t += velocity
        cur = nll_at(float(np.exp(log_t)))
        if cur < best_nll:
            best_nll = cur
            best_log_t = log_t
        if abs(grad) < tol:
            break

    # --- bounded grid search fallback ---------------------------------
    grid = np.exp(np.linspace(np.log(0.05), np.log(20.0), 200))
    grid_nlls = np.array([nll_at(float(t)) for t in grid])
    j = int(np.argmin(grid_nlls))
    if grid_nlls[j] < best_nll:
        best_nll = float(grid_nlls[j])
        best_log_t = float(np.log(grid[j]))

    temperature = float(np.exp(best_log_t))
    if not np.isfinite(temperature) or temperature <= 0:
        temperature = 1.0
        best_nll = nll_before

    return TemperatureScaler(
        temperature=temperature,
        n_classes=n_classes,
        nll_before=nll_before,
        nll_after=best_nll,
    )


def reliability_curve(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> dict[str, np.ndarray]:
    """Confidence-vs-accuracy reliability diagram data.

    Bins predictions by their top-class confidence. Returns a dict with:

    * ``bin_edges``: ``n_bins + 1`` edges over [0, 1].
    * ``bin_confidence``: mean confidence in each bin (0 where empty).
    * ``bin_accuracy``: fraction correct in each bin (0 where empty).
    * ``bin_counts``: number of samples in each bin.
    * ``bin_fraction``: bin count / total, which sums to 1.0.
    * ``fractions``: alias of ``bin_fraction`` (sums to 1).

    Works for multi-class: confidence is the max probability and accuracy is
    whether the argmax matches the true label.
    """
    mat = _as_2d(probs)
    if mat.shape[1] < 2:
        mat = _as_2d(np.column_stack([1.0 - mat[:, 0], mat[:, 0]]))
    conf = mat.max(axis=1)
    pred = mat.argmax(axis=1)
    idx = _labels_to_index(labels)
    correct = (pred == idx).astype(np.float64)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_confidence = np.zeros(n_bins)
    bin_accuracy = np.zeros(n_bins)
    bin_counts = np.zeros(n_bins, dtype=np.int64)

    # np.digitize with right=False gives 1..n_bins for values in (0,1].
    bin_ids = np.digitize(conf, edges[1:-1], right=False)
    for b in range(n_bins):
        mask = bin_ids == b
        c = int(mask.sum())
        bin_counts[b] = c
        if c:
            bin_confidence[b] = float(conf[mask].mean())
            bin_accuracy[b] = float(correct[mask].mean())

    total = max(1, len(conf))
    fractions = bin_counts.astype(np.float64) / total

    return {
        "bin_edges": edges,
        "bin_confidence": bin_confidence,
        "bin_accuracy": bin_accuracy,
        "bin_counts": bin_counts,
        "bin_fraction": fractions,
        "fractions": fractions,
    }


def expected_calibration_error(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE), the weighted mean |acc - conf|.

    ``ECE = sum_b (n_b / N) * |accuracy_b - confidence_b|``.
    """
    curve = reliability_curve(probs, labels, n_bins=n_bins)
    fractions = curve["bin_fraction"]
    gap = np.abs(curve["bin_accuracy"] - curve["bin_confidence"])
    return float(np.sum(fractions * gap))
