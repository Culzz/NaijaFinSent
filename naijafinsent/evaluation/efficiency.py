"""Cost, latency, and memory measurement — the E4 efficiency comparison.

What "efficiency" means for this project
----------------------------------------
A model that wins on macro-F1 by two points but costs 40x per document and adds a
second of latency may still be the wrong model to serve. E4 asks "small model vs
LLM on F1 vs cost vs latency", so this module produces three comparable numbers
per model:

* **latency** — mean / p50 / p95 per prediction and throughput (items/second),
* **memory** — peak traced allocation over the prediction call (approximate),
* **cost** — USD per 1 000 documents from token counts and published prices.

Honesty notes (carried into every report)
-----------------------------------------
* Latency on a developer laptop is not latency on the deployment host. We record
  ``repeats`` and report the *distribution*, and the report states the machine.
* Memory via ``tracemalloc`` measures **Python-level allocations only**. Weights
  held by native libraries (torch, onnxruntime) are invisible to it. When
  ``psutil`` is available we also record process RSS delta, which *does* see
  native memory, and label which number is which.
* Cost uses *observed* token counts when the model exposes them, otherwise a
  documented character heuristic. It is an estimate, not an invoice.
"""

from __future__ import annotations

import importlib.util
import statistics
import time
import tracemalloc
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

__all__ = [
    "time_predictions",
    "estimate_memory_mb",
    "cost_per_1k",
    "llm_cost_per_1k",
    "efficiency_table",
    "estimates_tokens",
    "HAS_PSUTIL",
]

# Does this interpreter have psutil? Checked once; never imported at module scope
# so the base install stays free of it.
HAS_PSUTIL: bool = importlib.util.find_spec("psutil") is not None

# Character-per-token heuristic used only when a model does not report tokens.
# English financial news tokenises at roughly 4 characters/token; the value is
# deliberately conservative so the cost estimate errs high rather than low.
CHARS_PER_TOKEN: float = 4.0


def estimates_tokens(text: str) -> int:
    """Best-effort token count for one input string.

    ``ceil(len(text) / 4)`` with a floor of 1 so an empty string still counts as
    one token. Documented as an approximation; prefer real tokenizer counts from
    the model when they are available.
    """
    return max(1, int(np.ceil(len(text) / CHARS_PER_TOKEN)))


def _percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile matching :func:`numpy.percentile`.

    Implemented locally so timing functions do not require numpy at call time and
    so the definition is explicit ("linear" interpolation, 0-100 scale).
    """
    if not values:
        raise ValueError("percentile of empty sequence")
    return float(np.percentile(np.asarray(values, dtype=float), pct, method="linear"))


# ---------------------------------------------------------------------------
# Latency / throughput
# ---------------------------------------------------------------------------

def time_predictions(
    model: Any,
    texts: Sequence[str],
    repeats: int = 3,
    *,
    batch_size: int | None = None,
    warmup: int = 1,
) -> dict[str, Any]:
    """Time ``model.predict(texts)`` and return latency + throughput statistics.

    Parameters
    ----------
    model
        Anything with ``.predict(texts) -> predictions``. Duck-typed on purpose so
        a TF-IDF baseline, a DistilBERT wrapper, and an LLM client are all
        measurable the same way.
    texts
        The exact documents to predict on. Pass the same list for every model or
        the latency comparison is meaningless.
    repeats
        Number of timed passes. Under 3 is not enough to see a p95.
    batch_size
        If given, ``texts`` is chunked and each chunk is a separate ``.predict``
        call — this is what a real API does, and it changes the per-item cost.
    warmup
        Untimed passes first, to pay import/lazy-init costs before measuring.
        Essential for transformer models whose first call loads weights.

    Returns
    -------
    ``{mean_ms, p50_ms, p95_ms, min_ms, max_ms, std_ms, per_item_mean_ms,
    throughput_items_per_sec, n_items, repeats, batch_size, latency_samples_ms}``

    Assumptions
    -----------
    * ``repeats`` passes are treated as independent samples of the same cost; we do
      not model drift within a long run. For runs over a minute, prefer more
      shorter passes so the samples bracket any thermal throttling.
    * ``batch_size`` affects throughput strongly (vectorisation) and per-item
      latency weakly (queueing); report which was used alongside the numbers.
    """
    if not texts:
        raise ValueError("time_predictions needs at least one text")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")

    items = list(texts)
    chunks = (
        [items]
        if batch_size is None
        else [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    )

    def _one_pass() -> float:
        start = time.perf_counter()
        for chunk in chunks:
            model.predict(chunk)
        return (time.perf_counter() - start) * 1000.0

    for _ in range(max(0, warmup)):
        _one_pass()

    samples = [_one_pass() for _ in range(repeats)]
    n_items = len(items)
    return {
        "mean_ms": float(statistics.fmean(samples)),
        "p50_ms": _percentile(samples, 50),
        "p95_ms": _percentile(samples, 95),
        "min_ms": float(min(samples)),
        "max_ms": float(max(samples)),
        "std_ms": float(statistics.pstdev(samples)) if len(samples) > 1 else 0.0,
        "per_item_mean_ms": float(statistics.fmean(samples)) / n_items,
        "throughput_items_per_sec": (n_items * 1000.0) / float(statistics.fmean(samples)),
        "n_items": n_items,
        "repeats": repeats,
        "batch_size": batch_size,
        "latency_samples_ms": [float(s) for s in samples],
    }


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def estimate_memory_mb(model_fn: Callable[[], Any]) -> dict[str, Any]:
    """Approximate peak memory used while producing a prediction.

    ``model_fn`` is a zero-argument callable that performs one representative
    prediction (e.g. ``lambda: model.predict(sample_texts)``). It is called inside
    ``tracemalloc`` so the **Python heap** peak is recorded.

    Returns
    -------
    ``{tracemalloc_peak_mb, tracemalloc_current_mb, rss_delta_mb, method, approximate}``

    * ``tracemalloc_peak_mb`` counts Python objects only. Model weights loaded by
      native code are *not* counted.
    * ``rss_delta_mb`` is process resident-set growth measured with ``psutil`` when
      installed, else ``None``. It sees native memory but includes noise from the
      rest of the process.
    * ``approximate`` is always ``True`` — the field exists so no consumer can
      accidentally quote these as exact, and ``method`` names what was measured.

    Assumption: the callable is side-effect-free enough to run once and be
    discarded. Peak, not steady-state, is reported because peak is what decides
    whether the container is sized correctly.
    """
    rss_before = _rss_mb()

    tracemalloc.start()
    try:
        model_fn()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    rss_after = _rss_mb()
    return {
        "tracemalloc_peak_mb": peak / (1024 * 1024),
        "tracemalloc_current_mb": current / (1024 * 1024),
        "rss_delta_mb": None if rss_before is None or rss_after is None
        else rss_after - rss_before,
        "method": "tracemalloc_python_heap"
        + ("+psutil_rss_delta" if rss_before is not None else ""),
        "psutil_available": HAS_PSUTIL,
        "approximate": True,
        "notes": (
            "tracemalloc sees Python-level allocations only; native library "
            "weights are not included. rss_delta_mb (when present) does include "
            "them but also process noise."
        ),
    }


def _rss_mb() -> float | None:
    """Resident set size in MiB, or ``None`` when psutil is unavailable."""
    if not HAS_PSUTIL:
        return None
    try:  # local import: optional dependency
        import psutil  # type: ignore[import-not-found]

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # pragma: no cover - defensive
        return None


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def cost_per_1k(
    input_tokens: float,
    output_tokens: float,
    price_in: float,
    price_out: float,
) -> float:
    """USD to process 1 000 documents at the given per-token prices.

    Parameters
    ----------
    input_tokens, output_tokens
        **Total** tokens for the 1 000 documents (not per document).
    price_in, price_out
        USD per **1 000 000 tokens** (the unit every provider publishes in).

    Returns
    -------
    USD for 1 000 documents::

        ((input_tokens / 1e6) * price_in + (output_tokens / 1e6) * price_out)

    Assumptions
    -----------
    * Prices are passed in, never looked up, so a stale constant can never make a
      report wrong; the report prints the price it used.
    * No caching, batching discount, or retry cost is modelled. For an LLM
      baseline we additionally report a "with prompt caching" variant at the call
      site if the provider offers it.
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    if price_in < 0 or price_out < 0:
        raise ValueError("prices must be non-negative")
    return (input_tokens / 1_000_000.0) * price_in + (output_tokens / 1_000_000.0) * price_out


def llm_cost_per_1k(
    texts: Sequence[str],
    price_in: float,
    price_out: float,
    *,
    output_tokens_per_doc: int = 8,
    token_counter: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    """Cost of one LLM pass over 1 000 documents, from the documents themselves.

    ``token_counter`` defaults to :func:`estimates_tokens`. ``output_tokens_per_doc``
    defaults to 8, which is enough for a short JSON verdict. The prompt overhead
    is not included; add it at the call site and say so in the report.
    """
    counter = token_counter or estimates_tokens
    n = len(texts)
    if n == 0:
        raise ValueError("llm_cost_per_1k needs at least one text")
    per_doc_in = float(np.mean([counter(t) for t in texts]))
    scale = 1000.0 / n
    total_in = per_doc_in * 1000.0
    total_out = float(output_tokens_per_doc) * 1000.0
    return {
        "input_tokens_per_1k": total_in,
        "output_tokens_per_1k": total_out,
        "usd_per_1k": cost_per_1k(total_in, total_out, price_in, price_out),
        "price_in_per_mtok": price_in,
        "price_out_per_mtok": price_out,
        "mean_input_tokens_per_doc": per_doc_in,
        "output_tokens_per_doc": output_tokens_per_doc,
        "n_texts_measured": n,
        "scale_factor": scale,
    }


# ---------------------------------------------------------------------------
# Table assembly
# ---------------------------------------------------------------------------

# Columns every E4 row must expose so the report table is always well-formed,
# even for a model where a measurement was impossible.
_REQUIRED_ROW_KEYS: tuple[str, ...] = (
    "model",
    "version",
    "task",
    "split",
    "macro_f1",
    "f1_ci_low",
    "f1_ci_high",
    "mean_ms",
    "p95_ms",
    "throughput_items_per_sec",
    "memory_mb",
    "usd_per_1k",
)


def efficiency_table(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise efficiency rows into a consistent, report-ready table.

    Each input row is a partial dict (a model may lack a cost, or a memory
    reading). This function fills every required column — ``None`` where a value
    genuinely could not be measured, which the renderer shows as ``n/a`` — and
    sorts by ``macro_f1`` descending with ``usd_per_1k`` ascending as the
    tie-break (a cheap model wins a tie, matching the model-selection criteria in
    ``docs/EVALUATION.md``).

    It never invents a number: missing stays missing. A row without a ``model``
    name raises, because an unattributable row is worse than no row.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("model"):
            raise ValueError(f"efficiency row is missing a model name: {row!r}")
        normalised: dict[str, Any] = {key: row.get(key) for key in _REQUIRED_ROW_KEYS}
        # Carry through any extra measurement the caller supplied.
        for key, value in row.items():
            normalised.setdefault(key, value)
        if normalised.get("memory_mb") is None:
            normalised["memory_mb"] = row.get("tracemalloc_peak_mb")
        out.append(normalised)

    def sort_key(r: dict[str, Any]) -> tuple[int, float, float]:
        f1 = r.get("macro_f1")
        cost = r.get("usd_per_1k")
        # Rows without an F1 sort last; rows without a cost are treated as free
        # only for ordering, never for reporting.
        return (
            0 if f1 is not None else 1,
            -(f1 if f1 is not None else 0.0),
            cost if cost is not None else 0.0,
        )

    return sorted(out, key=sort_key)
