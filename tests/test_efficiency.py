"""Tests for :mod:`naijafinsent.evaluation.efficiency`.

Latency cannot be asserted to an exact value, so the tests check *shape*
(all required keys), *determinism within tolerance* (repeat runs agree roughly),
and *cost arithmetic* (which is exact and must be exact).
"""

from __future__ import annotations

import time

import pytest

from naijafinsent.evaluation import efficiency as E


class CountingModel:
    """A tiny duck-typed model whose predict cost is a fixed sleep."""

    name = "counting"
    version = "test"
    task = "sentiment"

    def __init__(self, delay: float = 0.001) -> None:
        self.delay = delay
        self.calls = 0

    def predict(self, texts):
        self.calls += 1
        time.sleep(self.delay)
        return ["neutral"] * len(texts)


# ---------------------------------------------------------------------------
# time_predictions
# ---------------------------------------------------------------------------

def test_time_predictions_returns_expected_shape():
    model = CountingModel(delay=0.0)
    out = E.time_predictions(model, ["a", "b", "c", "d"], repeats=3, warmup=0)
    for key in (
        "mean_ms", "p50_ms", "p95_ms", "min_ms", "max_ms", "std_ms",
        "per_item_mean_ms", "throughput_items_per_sec", "n_items", "repeats",
        "latency_samples_ms",
    ):
        assert key in out, f"missing {key}"
    assert out["n_items"] == 4
    assert out["repeats"] == 3
    assert len(out["latency_samples_ms"]) == 3


def test_time_predictions_is_deterministic_within_tolerance():
    model = CountingModel(delay=0.002)
    a = E.time_predictions(model, ["x"] * 10, repeats=5, warmup=1)
    b = E.time_predictions(model, ["x"] * 10, repeats=5, warmup=1)
    # Steady-state timing is noisy; require the means to agree within a generous
    # factor. warmup=1 keeps lazy-import/cold-start cost out of the comparison
    # (a warmup=0 first record polluted the mean enough to flake under load).
    assert a["mean_ms"] == pytest.approx(b["mean_ms"], rel=0.5)


def test_time_predictions_min_max_bracket_the_mean():
    model = CountingModel(delay=0.001)
    out = E.time_predictions(model, ["x"] * 5, repeats=6, warmup=1)
    assert out["min_ms"] <= out["mean_ms"] <= out["max_ms"]
    assert out["min_ms"] <= out["p50_ms"] <= out["p95_ms"] <= out["max_ms"]


def test_batch_size_changes_number_of_predict_calls():
    model = CountingModel(delay=0.0)
    E.time_predictions(model, ["x"] * 10, repeats=1, batch_size=5, warmup=0)
    # 10 items / batch 5 = 2 calls
    assert model.calls == 2


def test_time_predictions_rejects_bad_input():
    with pytest.raises(ValueError):
        E.time_predictions(CountingModel(), [], repeats=1)
    with pytest.raises(ValueError):
        E.time_predictions(CountingModel(), ["a"], repeats=0)


def test_throughput_is_consistent_with_mean_latency():
    model = CountingModel(delay=0.0)
    out = E.time_predictions(model, ["x"] * 20, repeats=3, warmup=0)
    expected = (20 * 1000.0) / out["mean_ms"]
    assert out["throughput_items_per_sec"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# estimate_memory_mb
# ---------------------------------------------------------------------------

def test_estimate_memory_reports_peak_and_is_marked_approximate():
    out = E.estimate_memory_mb(lambda: [bytearray(100_000) for _ in range(10)])
    assert out["approximate"] is True
    assert out["tracemalloc_peak_mb"] > 0
    assert "tracemalloc_python_heap" in out["method"]
    # RSS delta is None only when psutil is unavailable.
    if not E.HAS_PSUTIL:
        assert out["rss_delta_mb"] is None


# ---------------------------------------------------------------------------
# Cost arithmetic (must be exact)
# ---------------------------------------------------------------------------

def test_cost_per_1k_exact_value():
    # 1,000,000 input tokens at $3/Mtok = $3.00
    # 500,000 output tokens at $15/Mtok = $7.50
    assert E.cost_per_1k(1_000_000, 500_000, 3.0, 15.0) == pytest.approx(10.5)


def test_cost_per_1k_zero_output():
    assert E.cost_per_1k(2_000_000, 0, 1.0, 99.0) == pytest.approx(2.0)


def test_cost_per_1k_rejects_negative_inputs():
    with pytest.raises(ValueError):
        E.cost_per_1k(-1, 0, 1.0, 1.0)
    with pytest.raises(ValueError):
        E.cost_per_1k(1, 0, -1.0, 1.0)


def test_llm_cost_per_1k_scales_to_a_thousand_documents():
    texts = ["a" * 400] * 50  # 100 tokens each at 4 chars/token
    out = E.llm_cost_per_1k(texts, price_in=3.0, price_out=15.0, output_tokens_per_doc=8)
    assert out["mean_input_tokens_per_doc"] == pytest.approx(100.0)
    assert out["input_tokens_per_1k"] == pytest.approx(100_000.0)
    assert out["output_tokens_per_1k"] == pytest.approx(8_000.0)
    expected = (100_000 / 1e6) * 3.0 + (8_000 / 1e6) * 15.0
    assert out["usd_per_1k"] == pytest.approx(expected)


def test_estimates_tokens_uses_documented_heuristic():
    assert E.estimates_tokens("a" * 400) == 100
    assert E.estimates_tokens("") == 1  # floor of one token


# ---------------------------------------------------------------------------
# efficiency_table
# ---------------------------------------------------------------------------

def test_efficiency_table_shape():
    rows = [
        {"model": "a", "macro_f1": 0.7, "usd_per_1k": 0.0, "mean_ms": 10.0,
         "p95_ms": 20.0, "throughput_items_per_sec": 100.0, "memory_mb": 50.0,
         "version": "1", "task": "sentiment", "split": "dev"},
    ]
    table = E.efficiency_table(rows)
    assert len(table) == 1
    for key in ("model", "version", "task", "split", "macro_f1", "f1_ci_low", "f1_ci_high",
                "mean_ms", "p95_ms", "throughput_items_per_sec", "memory_mb", "usd_per_1k"):
        assert key in table[0]


def test_efficiency_table_sorts_by_f1_then_cost():
    rows = [
        {"model": "low", "macro_f1": 0.60, "usd_per_1k": 0.0},
        {"model": "high-expensive", "macro_f1": 0.80, "usd_per_1k": 12.0},
        {"model": "high-cheap", "macro_f1": 0.80, "usd_per_1k": 0.01},
    ]
    table = E.efficiency_table(rows)
    assert [r["model"] for r in table] == ["high-cheap", "high-expensive", "low"]


def test_efficiency_table_unknown_cost_sorts_after_priced_model():
    rows = [
        {"model": "priced", "macro_f1": 0.8, "usd_per_1k": 1.0},
        {"model": "unmeasured", "macro_f1": 0.8},
    ]
    table = E.efficiency_table(rows)
    # Unknown cost is not treated as free.
    assert table[0]["model"] == "priced"


def test_efficiency_table_requires_a_model_name():
    with pytest.raises(ValueError):
        E.efficiency_table([{"macro_f1": 0.5}])


def test_efficiency_table_never_invents_missing_values():
    table = E.efficiency_table([{"model": "a", "macro_f1": 0.5}])
    assert table[0]["usd_per_1k"] is None
    assert table[0]["memory_mb"] is None
