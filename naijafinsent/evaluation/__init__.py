"""NaijaFinSent evaluation harness.

Public surface, in the order a reader should meet it:

* :mod:`naijafinsent.evaluation.metrics` — metric families (classification, NER,
  events, calibration) plus bootstrap CIs and paired significance tests.
* :mod:`naijafinsent.evaluation.slices` — per-slice and drift reporting.
* :mod:`naijafinsent.evaluation.error_analysis` — the error taxonomy and queue.
* :mod:`naijafinsent.evaluation.efficiency` — cost / latency / memory for E4.
* :mod:`naijafinsent.evaluation.registry` — the append-only run log + leaderboard.
* :mod:`naijafinsent.evaluation.runner` — the CLI and the locked-test guard.

Heavy submodules are imported lazily: importing this package for a quick metric
must not drag in pandas, subprocess, or anything else.
"""

from __future__ import annotations

__all__ = [
    "metrics",
    "slices",
    "error_analysis",
    "efficiency",
    "registry",
    "runner",
]
