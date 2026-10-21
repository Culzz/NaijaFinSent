"""Tests for probability calibration (temperature scaling + ECE)."""

from __future__ import annotations

import numpy as np

from naijafinsent.sentiment.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
    negative_log_likelihood,
    reliability_curve,
)


def _overconfident_probs(seed: int = 0, n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic over-confident binary probabilities with known true labels."""
    rng = np.random.default_rng(seed)
    # Latent correctness correlated with a noisy true probability.
    true_p = rng.uniform(0.5, 1.0, size=n)
    correct = rng.random(n) < true_p
    labels = np.where(correct, 1, 0)
    # Model is over-confident: push probabilities toward the extremes.
    raw = np.clip(0.5 + (true_p - 0.5) * 2.5, 0.001, 0.999)
    probs = np.where(correct, raw, 1.0 - raw)
    return probs, labels


def _multiclass_overconfident(seed: int = 1, n: int = 400, k: int = 4):
    rng = np.random.default_rng(seed)
    logits = rng.normal(size=(n, k)) * 2.0
    labels = logits.argmax(axis=1)
    # Flip some labels to make the model imperfect but still informative.
    flip = rng.random(n) < 0.2
    labels = np.where(flip, (labels + 1) % k, labels)
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    return probs, labels


class TestTemperatureScaling:
    def test_improves_or_preserves_ece_binary(self) -> None:
        probs, labels = _overconfident_probs()
        ece_before = expected_calibration_error(probs, labels, n_bins=10)
        scaler = fit_temperature(probs, labels)
        calibrated = apply_temperature(probs, scaler.temperature)
        ece_after = expected_calibration_error(calibrated, labels, n_bins=10)
        # Calibration must not make things worse.
        assert ece_after <= ece_before + 1e-6
        assert scaler.improved

    def test_softens_overconfident_binary(self) -> None:
        probs, labels = _overconfident_probs()
        scaler = fit_temperature(probs, labels)
        # Over-confident inputs should be softened (T > 1).
        assert scaler.temperature > 1.0

    def test_multiclass_nll_not_worse(self) -> None:
        probs, labels = _multiclass_overconfident()
        nll_before = negative_log_likelihood(np.log(probs + 1e-12), labels)
        scaler = fit_temperature(probs, labels)
        assert scaler.nll_after <= nll_before + 1e-9

    def test_temperature_positive_and_finite(self) -> None:
        probs, labels = _overconfident_probs()
        scaler = fit_temperature(probs, labels)
        assert np.isfinite(scaler.temperature)
        assert scaler.temperature > 0

    def test_apply_temperature_returns_probabilities(self) -> None:
        probs, _ = _overconfident_probs()
        out = apply_temperature(probs, 2.0)
        assert out.shape == (len(probs), 2)
        assert np.allclose(out.sum(axis=1), 1.0)

    def test_invalid_temperature_raises(self) -> None:
        probs, _ = _overconfident_probs()
        try:
            apply_temperature(probs, 0.0)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected ValueError for temperature <= 0")


class TestReliabilityCurve:
    def test_fractions_sum_to_one(self) -> None:
        probs, labels = _overconfident_probs()
        curve = reliability_curve(probs, labels, n_bins=10)
        assert abs(curve["bin_fraction"].sum() - 1.0) < 1e-9
        assert abs(curve["fractions"].sum() - 1.0) < 1e-9

    def test_bin_edges(self) -> None:
        probs, labels = _overconfident_probs()
        curve = reliability_curve(probs, labels, n_bins=5)
        assert len(curve["bin_edges"]) == 6
        assert curve["bin_edges"][0] == 0.0
        assert curve["bin_edges"][-1] == 1.0

    def test_counts_sum_to_n(self) -> None:
        probs, labels = _overconfident_probs(n=250)
        curve = reliability_curve(probs, labels, n_bins=10)
        assert curve["bin_counts"].sum() == 250

    def test_multiclass(self) -> None:
        probs, labels = _multiclass_overconfident()
        curve = reliability_curve(probs, labels, n_bins=10)
        assert abs(curve["bin_fraction"].sum() - 1.0) < 1e-9
        assert np.all(curve["bin_accuracy"] >= 0.0)
        assert np.all(curve["bin_accuracy"] <= 1.0)
