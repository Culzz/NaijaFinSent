"""The evaluation registry: every run is appended, nothing is overwritten.

Why append-only JSONL
---------------------
A leaderboard that can be silently edited is not evidence. Each evaluation run is
appended as one JSON object to ``research/reports/runs.jsonl`` with enough
provenance to reproduce and challenge it:

* **model** name + version, **task**, **split**, **seed**
* the **metrics** themselves (with CIs where the caller has them)
* **params** (hyperparameters, prompt template id, temperature, …)
* a UTC **timestamp**
* the **git sha** of the working tree (or ``None`` outside a repo)
* a **dataset version/hash**, so "we improved by 3 points" can be checked against
  the exact evaluation set it was measured on.

Runs are never deleted or rewritten; correcting a mistake means appending a new
run with a higher ``run_id``. The leaderboard reads the file and always uses the
latest run per ``(model, version, task, split)`` key unless told otherwise.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from naijafinsent.config import REPO_ROOT
from naijafinsent.utils import utcnow

__all__ = [
    "RUNS_PATH",
    "REQUIRED_RUN_FIELDS",
    "RunRecord",
    "dataset_hash",
    "git_sha",
    "log_run",
    "load_runs",
    "leaderboard",
    "select_best",
    "run_id",
]

# Default home of the append-only run log. Lives beside the reports so the
# machine-readable and human-readable artefacts travel together.
RUNS_PATH: Path = REPO_ROOT / "research" / "reports" / "runs.jsonl"

# Every run record must carry these fields. Enforced in ``log_run`` so a malformed
# record fails loudly at write time rather than silently poisoning the leaderboard.
REQUIRED_RUN_FIELDS: tuple[str, ...] = (
    "run_id",
    "model",
    "version",
    "task",
    "split",
    "seed",
    "metrics",
    "params",
    "timestamp",
    "git_sha",
    "dataset_version",
    "dataset_hash",
)

# Default tie-break order when F1 is equal: cheaper wins, then faster, then the
# earlier run (stability). Documented here because "which model won" must be
# reproducible from the criteria alone, not from table order.
DEFAULT_TIE_BREAK: tuple[str, ...] = ("usd_per_1k", "per_item_mean_ms", "timestamp")


def dataset_hash(version: str | None = None) -> str:
    """Hash the evaluation-set version string into a short, stable digest.

    The digest is what makes two runs comparable: if the hash matches, the numbers
    were computed on the same declared dataset. ``None`` hashes to the digest of
    the literal string ``"unversioned"`` so the field is never empty — an
    unversioned run is a fact worth recording, not a missing value.
    """
    material = version if version else "unversioned"
    return hashlib.sha256(str(material).encode("utf-8")).hexdigest()[:16]


def git_sha(short: bool = True) -> str | None:
    """Return the current git commit sha, or ``None`` when not in a repo.

    Silent on failure (dirty trees, a repo with no commits, git not installed):
    provenance is valuable but its absence must never break an experiment.
    """
    try:
        args = ["git", "rev-parse"]
        if short:
            args.append("--short")
        args.append("HEAD")
        result = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - env dependent
        return None
    sha = result.stdout.strip()
    return sha or None


def run_id(prefix: str = "run") -> str:
    """A short, sortable-ish unique id: ``run-<utcstamp>-<6 hex>``."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


@dataclass
class RunRecord:
    """Typed view of one run. Serialises to the dict stored in ``runs.jsonl``."""

    model: str
    task: str
    split: str
    metrics: dict[str, Any]
    version: str = "unknown"
    seed: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    dataset_version: str | None = None
    git_sha: str | None = None
    timestamp: str | None = None
    run_id: str | None = None
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "run_id": self.run_id or run_id(),
            "model": self.model,
            "version": self.version,
            "task": self.task,
            "split": self.split,
            "seed": self.seed,
            "metrics": dict(self.metrics),
            "params": dict(self.params),
            "timestamp": self.timestamp or utcnow().isoformat(),
            "git_sha": self.git_sha if self.git_sha is not None else git_sha(),
            "dataset_version": self.dataset_version,
            "dataset_hash": dataset_hash(self.dataset_version),
            "notes": self.notes,
        }
        record.update(self.extra)
        return record


def log_run(run: dict[str, Any] | RunRecord, path: str | Path | None = None) -> dict[str, Any]:
    """Append one run to the registry and return the stored record.

    Accepts either an already-built dict or a :class:`RunRecord`. Missing
    provenance (``timestamp``, ``git_sha``, ``dataset_hash``, ``run_id``) is
    filled in; a missing *required* field raises ``ValueError``.

    Assumptions
    -----------
    * The process writing has, or can create, ``research/reports/``.
    * Appends are line-atomic on the platforms we target; we do not lock, because
      parallel evaluation runs are serialised by the runner, and a corrupted line
      is detectable (and skippable) by :func:`load_runs`.
    """
    target = Path(path) if path is not None else RUNS_PATH
    record = run.to_dict() if isinstance(run, RunRecord) else _complete_record(dict(run))

    missing = [f for f in REQUIRED_RUN_FIELDS if f not in record or record[f] is None]
    # dataset_version may legitimately be None (recorded as unversioned); hash is not.
    missing = [m for m in missing if m != "dataset_version"]
    if missing:
        raise ValueError(f"run record is missing required fields: {missing}")

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record


def _complete_record(record: dict[str, Any]) -> dict[str, Any]:
    record.setdefault("run_id", run_id())
    record.setdefault("version", "unknown")
    record.setdefault("seed", 0)
    record.setdefault("params", {})
    record.setdefault("metrics", {})
    record.setdefault("timestamp", utcnow().isoformat())
    record.setdefault("git_sha", git_sha())
    record.setdefault("dataset_version", None)
    record.setdefault("dataset_hash", dataset_hash(record.get("dataset_version")))
    return record


def load_runs(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read every run, skipping blank or unparseable lines.

    A corrupt line is skipped rather than raising, because a single bad append
    must not take down the whole leaderboard. Malformed lines are silently
    dropped here and surfaced by the report builder, which counts them.
    """
    target = Path(path) if path is not None else RUNS_PATH
    if not target.exists():
        return []
    runs: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return runs


def _metric_value(run: dict[str, Any], metric: str) -> float | None:
    """Pull a metric out of a run, tolerating ``{"value": …, "ci_low": …}`` shapes."""
    raw = (run.get("metrics") or {}).get(metric)
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("value", raw.get("point"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _latest_per_key(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the most recent run per (model, version, task, split).

    Recency is by ``timestamp`` and falls back to file order (later wins), so a
    re-run of the same configuration supersedes the old one on the leaderboard
    without erasing the history in the file.
    """
    latest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for run in runs:
        key = (run.get("model"), run.get("version"), run.get("task"), run.get("split"))
        current = latest.get(key)
        if current is None or str(run.get("timestamp") or "") >= str(
            current.get("timestamp") or ""
        ):
            latest[key] = run
    return list(latest.values())


def leaderboard(
    task: str,
    metric: str = "macro_f1",
    split: str = "test_random",
    *,
    path: str | Path | None = None,
    include_history: bool = False,
) -> list[dict[str, Any]]:
    """Rank models for one ``(task, split)`` by ``metric``, best first.

    Only runs whose ``metrics`` actually contain ``metric`` are ranked; a run that
    measured something else is excluded rather than treated as zero. Ordering is
    by metric descending, then by :data:`DEFAULT_TIE_BREAK`.

    With ``include_history=True`` every historical run is ranked (useful to see
    regressions across versions); the default keeps the newest run per key.
    """
    runs = load_runs(path)
    candidates = [
        r
        for r in runs
        if r.get("task") == task and r.get("split") == split and _metric_value(r, metric) is not None
    ]
    if not include_history:
        candidates = _latest_per_key(candidates)

    ranked = sorted(candidates, key=lambda r: _leaderboard_sort_key(r, metric))
    table: list[dict[str, Any]] = []
    for rank, run in enumerate(ranked, start=1):
        row = {
            "rank": rank,
            "model": run.get("model"),
            "version": run.get("version"),
            "task": run.get("task"),
            "split": run.get("split"),
            "seed": run.get("seed"),
            "metric": metric,
            "value": _metric_value(run, metric),
            "run_id": run.get("run_id"),
            "timestamp": run.get("timestamp"),
            "git_sha": run.get("git_sha"),
            "dataset_hash": run.get("dataset_hash"),
        }
        metrics = run.get("metrics") or {}
        raw = metrics.get(metric) if isinstance(metrics, dict) else None
        if isinstance(raw, dict):
            row["ci_low"] = raw.get("ci_low", raw.get("low"))
            row["ci_high"] = raw.get("ci_high", raw.get("high"))
        # Carry the tie-break inputs so the ordering is auditable.
        for key in DEFAULT_TIE_BREAK:
            row[key] = _run_scalar(run, key)
        table.append(row)
    return table


def _run_scalar(run: dict[str, Any], key: str) -> Any:
    """Look for a scalar at top level, then under ``metrics``/``params``."""
    if key in run and not isinstance(run[key], (dict, list)):
        return run[key]
    for container in ("metrics", "params", "timing", "cost"):
        block = run.get(container)
        if isinstance(block, dict) and key in block and not isinstance(block[key], (dict, list)):
            return block[key]
    return None


def _leaderboard_sort_key(run: dict[str, Any], metric: str) -> tuple[float, float, float, str]:
    value = _metric_value(run, metric) or 0.0
    cost = _run_scalar(run, "usd_per_1k")
    latency = _run_scalar(run, "per_item_mean_ms")
    return (
        -value,
        float(cost) if cost is not None else float("inf"),
        float(latency) if latency is not None else float("inf"),
        str(run.get("timestamp") or ""),
    )


def select_best(
    task: str,
    metric: str = "macro_f1",
    split: str = "test_random",
    *,
    path: str | Path | None = None,
    min_value: float | None = None,
    tie_break: tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    """Return the winning run for a task, honouring a documented tie-break.

    Decision rule (also written into ``docs/EVALUATION.md``):

    1. Highest ``metric`` on the given ``split`` wins.
    2. If two runs are within ``TIE_EPSILON`` (1e-9 — exact ties only, since the
       report compares overlapping CIs rather than this helper), the **cheaper**
       model wins on ``usd_per_1k``.
    3. Then the **faster** model on ``per_item_mean_ms``.
    4. Then the earlier run ``timestamp`` (stability: prefer the incumbent).

    ``min_value`` lets a caller demand a floor before anything can win (e.g. only
    consider models above the majority-class baseline); if nothing clears it,
    ``None`` is returned rather than the least-bad option. Returns ``None`` when
    the leaderboard is empty.
    """
    order = tie_break or DEFAULT_TIE_BREAK
    table = leaderboard(task, metric, split, path=path)
    if min_value is not None:
        table = [row for row in table if (row.get("value") or 0.0) >= min_value]
    if not table:
        return None

    top_value = table[0]["value"]

    def tie_key(row: dict[str, Any]) -> tuple[float, float, str]:
        values: list[float] = []
        for key in order:
            if key == "timestamp":
                continue
            raw = row.get(key)
            values.append(float(raw) if raw is not None else float("inf"))
        while len(values) < 2:
            values.append(float("inf"))
        return (values[0], values[1], str(row.get("timestamp") or ""))

    tied = [row for row in table if abs((row["value"] or 0.0) - (top_value or 0.0)) < 1e-9]
    winner = sorted(tied, key=tie_key)[0]
    winner = dict(winner)
    winner["tie_break"] = list(order)
    winner["selection_rule"] = (
        f"highest {metric} on {split}; ties broken by " + " then ".join(order)
    )
    return winner
