"""Experiment orchestration and the locked-test guard.

Two responsibilities live here.

1. **The locked-test guard** (:func:`evaluate_locked_once`). The project commits
   to evaluating the locked test set *exactly once* for the final report. A
   convention is not enough — a convention is what everyone intends to follow
   right up until the deadline. So the guard is code: the first call writes a
   state file recording that the lock was spent; every later call refuses unless
   the caller passes ``force=True``, which the CLI only wires to the explicit flag
   ``--force-i-know-this-breaks-the-protocol``. The state file is append-only, so
   an incautious override is permanently visible.

2. **The CLI** (``python -m naijafinsent.evaluation.runner``) with three commands:
   ``bench``, ``experiments``, ``report``.

Import discipline
-----------------
Sibling packages (``baselines``, ``sentiment``, ``ner``, …) may not exist yet while
this harness is being built. Every import of theirs happens **inside a function**
and is wrapped so that a missing module degrades to a printed
``requires trained model X; skipping`` message. Nothing here ever fabricates a
metric; a missing dependency produces a skip, not a zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from naijafinsent.config import REPO_ROOT
from naijafinsent.evaluation import metrics as M
from naijafinsent.evaluation import registry
from naijafinsent.utils import utcnow

__all__ = [
    "LockedTestError",
    "LOCK_STATE_PATH",
    "locked_state",
    "evaluate_locked_once",
    "reset_lock_for_tests",
    "main",
]

REPORTS_DIR: Path = REPO_ROOT / "research" / "reports"
EXPERIMENTS_DIR: Path = REPO_ROOT / "research" / "experiments"
# Where the guard remembers that the lock has been spent. Deliberately a plain
# JSON file: auditable with any text editor, no database, no hidden state.
LOCK_STATE_PATH: Path = REPORTS_DIR / "locked_test_state.json"

# The flag that intentionally breaks the protocol. Its only job is to be long
# enough that nobody types it by accident.
FORCE_FLAG: str = "--force-i-know-this-breaks-the-protocol"


class LockedTestError(RuntimeError):
    """Raised when the locked test set is evaluated a second time without force."""


# ---------------------------------------------------------------------------
# The locked-test guard
# ---------------------------------------------------------------------------

def locked_state(path: str | Path | None = None) -> dict[str, Any]:
    """Read the lock state without modifying it.

    Returns ``{"spent": bool, "evaluations": [...]}``. ``evaluations`` is the full
    history of every locked-set evaluation, so a forced re-run does not hide the
    earlier one — it appends to it.
    """
    target = Path(path) if path is not None else LOCK_STATE_PATH
    if not target.exists():
        return {"spent": False, "evaluations": []}
    try:
        state = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A corrupt state file must fail *closed*: treat it as spent, because
        # assuming "not spent" would let a second evaluation slip through.
        return {
            "spent": True,
            "evaluations": [],
            "corrupt": True,
            "note": "state file unreadable; failing closed",
        }
    state.setdefault("spent", bool(state.get("evaluations")))
    state.setdefault("evaluations", [])
    return state


def evaluate_locked_once(
    evaluate_fn: Callable[[], Any],
    *,
    force: bool = False,
    reason: str = "",
    state_path: str | Path | None = None,
) -> Any:
    """Run ``evaluate_fn`` against the locked test set — at most once, ever.

    Parameters
    ----------
    evaluate_fn
        A zero-argument callable that performs the real locked-set evaluation and
        returns its result (a metrics dict, typically).
    force
        Only the CLI's explicit protocol-breaking flag sets this. When ``True``
        the evaluation runs, but the state records that it was forced, with the
        ``reason`` and a timestamp.
    reason
        Free-text justification, mandatory in spirit when ``force=True`` (it is
        recorded verbatim; empty is allowed but discouraged and flagged).

    Raises
    ------
    LockedTestError
        If the lock is already spent and ``force`` is not set. The message names
        the date of the original evaluation so the caller can find it.

    Returns
    -------
    Whatever ``evaluate_fn`` returned.

    Assumptions
    -----------
    * ``state_path`` is on a filesystem shared across the machines that might run
      this. For this project that is the repo checkout; if evaluation ever moves
      to ephemeral CI, the state must be committed back or the guard is defeatable.
    * The guard protects against *accidental* re-use (a rerun loop, a colleague
      re-executing the report command). A determined person can delete the state
      file; the append-only ``evaluations`` list plus the git sha recorded in each
      evaluation is the detection mechanism for that case, not prevention.
    """
    path = Path(state_path) if state_path is not None else LOCK_STATE_PATH
    state = locked_state(path)

    if state.get("spent") and not force:
        first = state["evaluations"][0] if state.get("evaluations") else {}
        when = first.get("timestamp", "an earlier date")
        raise LockedTestError(
            "locked test set has already been evaluated ("
            f"{when}, run_id={first.get('run_id', 'unknown')}). "
            "Refusing to evaluate again. The locked test is evaluated once for "
            f"the final report; pass {FORCE_FLAG} only if you are deliberately "
            "breaking the protocol, and record why."
        )

    entry = {
        "run_id": registry.run_id(prefix="locked"),
        "timestamp": utcnow().isoformat(),
        "forced": bool(force),
        "previous_evaluations": len(state.get("evaluations", [])),
        "reason": reason,
        "git_sha": registry.git_sha(),
    }
    result = evaluate_fn()
    entry["summary"] = _summarise_result(result)

    # Persist *after* the evaluation so a crash mid-run does not burn the lock
    # without producing a result, but before returning so a crash after the run
    # still records that the lock was spent.
    history = list(state.get("evaluations", []))
    history.append(entry)
    _write_state(path, {"spent": True, "evaluations": history})
    return result


def _summarise_result(result: Any) -> Any:
    """Reduce an evaluation result to something safely JSON-serialisable."""
    if isinstance(result, dict):
        return {k: _summarise_result(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [_summarise_result(v) for v in result][:20]
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    return str(result)


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_lock_for_tests(state_path: str | Path | None = None) -> None:
    """Delete the lock state. Test-only helper — never called from the CLI.

    Named with the ``_for_tests`` suffix so it is obvious in review that touching
    it in production code is a bug.
    """
    path = Path(state_path) if state_path is not None else LOCK_STATE_PATH
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Baseline discovery (defensive)
# ---------------------------------------------------------------------------

@dataclass
class ModelHandle:
    """A duck-typed model the harness can evaluate.

    We only require ``.predict``; ``.name`` / ``.version`` / ``.task`` are read
    with sensible fallbacks so a bare function wrapped in a tiny adapter works.
    """

    obj: Any
    name: str = "unknown"
    version: str = "unknown"
    task: str = "sentiment"
    extra: dict[str, Any] = field(default_factory=dict)


def discover_baselines() -> tuple[list[ModelHandle], str | None]:
    """Try to load models from ``naijafinsent.baselines``.

    Returns ``(handles, reason_if_empty)``. The whole import is defensive: the
    ``baselines`` package is owned by another agent and may not exist, may be
    empty, or may not expose a registry yet. Any failure returns an explanatory
    string instead of raising, so ``bench`` can print a clear skip message.
    """
    try:
        from naijafinsent import baselines  # noqa: PLC0415  (deliberately local)
    except ImportError as exc:
        return [], f"naijafinsent.baselines not importable yet ({exc})"

    registry_fn = getattr(baselines, "available_models", None) or getattr(
        baselines, "load_models", None
    )
    if registry_fn is None:
        return [], (
            "naijafinsent.baselines exists but exposes neither available_models() "
            "nor load_models(); nothing to benchmark yet"
        )

    try:
        found = registry_fn()
    except Exception as exc:  # pragma: no cover - depends on sibling package
        return [], f"naijafinsent.baselines failed to load models ({exc})"

    handles: list[ModelHandle] = []
    for item in found or []:
        if isinstance(item, ModelHandle):
            handles.append(item)
            continue
        handles.append(
            ModelHandle(
                obj=item,
                name=str(getattr(item, "name", type(item).__name__)),
                version=str(getattr(item, "version", "unknown")),
                task=str(getattr(item, "task", "sentiment")),
            )
        )
    if not handles:
        return [], "naijafinsent.baselines returned an empty model list"
    return handles, None


# ---------------------------------------------------------------------------
# Dataset loading (defensive)
# ---------------------------------------------------------------------------

@dataclass
class EvalDataset:
    """The minimum an experiment needs: aligned texts, gold, and samples."""

    texts: list[str]
    gold: list[Any]
    samples: list[Any]
    split: str = "dev"
    dataset_version: str | None = None

    def __len__(self) -> int:
        return len(self.texts)


def load_split(split: str, *, limit: int | None = None) -> tuple[EvalDataset | None, str | None]:
    """Best-effort load of an annotated split for evaluation.

    Tries the annotation/data owners' loaders if present, else any JSONL under
    ``data/`` that matches the split name. Returns ``(dataset, None)`` or
    ``(None, reason)``. Never raises for a missing dependency — a harness that
    crashes because a sibling module is early is useless during a build-out.

    Assumptions
    -----------
    * A usable record has ``text`` and either a ``sentiment`` label or a ``label``
      field. Anything else is skipped with a count reported in the reason.
    """
    try:
        from naijafinsent.annotation import load_annotations  # noqa: PLC0415

        records = load_annotations(split=split)
        dataset = _dataset_from_records(records, split=split, limit=limit)
        if dataset is not None:
            return dataset, None
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - depends on sibling package
        return None, f"annotation loader failed for split={split!r}: {exc}"

    # Fall back to a JSONL file matching the split name under data/.
    candidate = REPO_ROOT / "data" / f"{split}.jsonl"
    if candidate.exists():
        records = _read_jsonl(candidate)
        dataset = _dataset_from_records(records, split=split, limit=limit)
        if dataset is not None:
            return dataset, None

    return None, (
        f"no annotated data available for split={split!r}; "
        "expected naijafinsent.annotation.load_annotations or data/<split>.jsonl"
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _dataset_from_records(
    records: Sequence[Any] | None, *, split: str, limit: int | None
) -> EvalDataset | None:
    if not records:
        return None
    texts: list[str] = []
    gold: list[Any] = []
    samples: list[Any] = []
    for record in records:
        text = _field(record, "text", "content")
        label = _sentiment_label(record)
        if text is None or label is None:
            continue
        texts.append(str(text))
        gold.append(label)
        samples.append(record)
    if not texts:
        return None
    if limit is not None:
        texts, gold, samples = texts[:limit], gold[:limit], samples[:limit]
    version = f"{split}:sha256:{_dataset_digest(texts)}"
    return EvalDataset(texts=texts, gold=gold, samples=samples, split=split,
                       dataset_version=version)


def _dataset_digest(texts: Sequence[str]) -> str:
    import hashlib

    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
    return digest.hexdigest()[:16]


def _field(record: Any, *names: str) -> Any:
    for name in names:
        if isinstance(record, dict) and record.get(name) is not None:
            return record[name]
        if hasattr(record, name) and getattr(record, name) is not None:
            return getattr(record, name)
    return None


def _sentiment_label(record: Any) -> str | None:
    """Pull a sentiment label from the many shapes annotation records take."""
    sentiment = _field(record, "sentiment", "label", "sentiment_label")
    if sentiment is None:
        return None
    if isinstance(sentiment, str):
        return sentiment
    if isinstance(sentiment, dict):
        return sentiment.get("label")
    return getattr(sentiment, "label", None)


# ---------------------------------------------------------------------------
# Evaluation of one model on one dataset
# ---------------------------------------------------------------------------

def evaluate_model(
    model: ModelHandle,
    dataset: EvalDataset,
    *,
    seed: int = 0,
    n_bootstrap: int = 1000,
    log: bool = True,
) -> dict[str, Any]:
    """Predict, score, interval, and (optionally) log one model on one dataset.

    Produces the metric families the report needs when the task is ``sentiment``:
    macro-F1 with a bootstrap CI, accuracy, and the per-class table. Every number
    carries the seed and the CI so nothing is quoted bare.

    Returns a run-shaped dict (see :data:`registry.REQUIRED_RUN_FIELDS`).
    """
    preds = _call_predict(model.obj, dataset.texts)

    metrics: dict[str, Any] = {}
    if model.task in {"sentiment", "entity_sentiment"}:
        fn = M.macro_f1_metric(M.DEFAULT_LABELS)
        ci = M.bootstrap_ci(fn, dataset.gold, preds, n=n_bootstrap, seed=seed)
        metrics["macro_f1"] = {
            "value": ci["point"],
            "ci_low": ci["low"],
            "ci_high": ci["high"],
            "std": ci["std"],
            "n": ci["n"],
        }
        metrics["accuracy"] = M.accuracy(dataset.gold, preds)
        metrics["per_class"] = M.per_class_prf(dataset.gold, preds, M.DEFAULT_LABELS)
    else:
        # Unknown task family: report accuracy only rather than guess a metric.
        metrics["accuracy"] = M.accuracy(dataset.gold, preds)

    run = registry.RunRecord(
        model=model.name,
        version=model.version,
        task=model.task,
        split=dataset.split,
        seed=seed,
        metrics=metrics,
        params=model.extra.get("params", {}),
        dataset_version=dataset.dataset_version,
    ).to_dict()
    if log:
        registry.log_run(run)
    return run


def _call_predict(model: Any, texts: Sequence[str]) -> list[Any]:
    """Call ``model.predict`` with a list, tolerating scalar-only interfaces."""
    if not hasattr(model, "predict"):
        raise TypeError(f"model {model!r} has no .predict method")
    result = model.predict(list(texts))
    if isinstance(result, (str, int, float)) or not hasattr(result, "__iter__"):
        return [result]
    out: list[Any] = []
    for item in result:
        out.append(getattr(item, "label", item))
    return out


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _render_leaderboard_table(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        return "_No runs logged yet._\n"
    lines = [
        "| rank | model | version | split | metric | value | 95% CI | seed | run_id |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        ci = ""
        if row.get("ci_low") is not None and row.get("ci_high") is not None:
            ci = f"[{row['ci_low']:.3f}, {row['ci_high']:.3f}]"
        value = row.get("value")
        value_s = f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"
        lines.append(
            f"| {row['rank']} | {row['model']} | {row['version']} | {row['split']} "
            f"| {row['metric']} | {value_s} | {ci} | {row.get('seed')} | {row.get('run_id')} |"
        )
    return "\n".join(lines) + "\n"


def build_report(*, task: str = "sentiment", split: str = "dev", metric: str = "macro_f1") -> dict[str, Any]:
    """Assemble the machine-readable evaluation report plus its Markdown.

    Writes ``research/reports/evaluation.json`` and
    ``research/reports/leaderboard.md``. The human Stage 8 narrative lives in
    ``docs/EVALUATION.md`` and is edited by hand from these artefacts — this
    function never overwrites prose.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = registry.leaderboard(task, metric, split)
    best = registry.select_best(task, metric, split)
    state = locked_state()

    payload = {
        "generated_at": utcnow().isoformat(),
        "task": task,
        "split": split,
        "metric": metric,
        "n_runs_total": len(registry.load_runs()),
        "leaderboard": rows,
        "selected": best,
        "locked_test": {
            "spent": state.get("spent", False),
            "n_evaluations": len(state.get("evaluations", [])),
            "evaluations": state.get("evaluations", []),
        },
    }

    json_path = REPORTS_DIR / "evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Evaluation leaderboard (machine-generated)",
        "",
        f"_Generated {payload['generated_at']} by `naijafinsent.evaluation.runner report`._",
        "",
        f"**Task:** `{task}` · **Split:** `{split}` · **Metric:** `{metric}`",
        "",
        "Locked test set: "
        + ("**already evaluated** (see `locked_test_state.json`)."
           if state.get("spent") else "not yet evaluated."),
        "",
        _render_leaderboard_table(rows),
        "",
    ]
    if best:
        md += [
            "## Selected model",
            "",
            f"- **{best['model']}** v{best['version']} — {metric} = "
            f"{best['value']:.4f} on `{split}`",
            f"- Selection rule: {best['selection_rule']}",
            "",
        ]
    (REPORTS_DIR / "leaderboard.md").write_text("\n".join(md), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_bench(args: argparse.Namespace) -> int:
    handles, reason = discover_baselines()
    if reason:
        print(f"[bench] skipping: {reason}")
        print("[bench] This is expected until naijafinsent.baselines is implemented.")
        return 0

    dataset, data_reason = load_split(args.split, limit=args.limit)
    if dataset is None:
        print(f"[bench] skipping: {data_reason}")
        return 0

    print(f"[bench] {len(handles)} model(s) on split={args.split!r} ({len(dataset)} items)")
    logged = 0
    for handle in handles:
        try:
            run = evaluate_model(
                handle, dataset, seed=args.seed, n_bootstrap=args.bootstrap, log=not args.no_log
            )
        except Exception as exc:
            print(f"[bench]   {handle.name}: FAILED ({exc})")
            continue
        f1 = run["metrics"].get("macro_f1", {}).get("value")
        print(f"[bench]   {handle.name} v{handle.version}: macro_f1={f1}")
        logged += 1
    print(f"[bench] done — {logged} run(s) logged to {registry.RUNS_PATH}")
    return 0


def _cmd_experiments(args: argparse.Namespace) -> int:
    """Run the E1–E9 scripts in ``research/experiments`` as separate processes.

    Each script owns its own argparse and its own report artefact, so the runner
    only needs to launch them with the right seed and split, and to report which
    ones could not run because a trained model was missing.
    """
    scripts = sorted(EXPERIMENTS_DIR.glob("e[0-9]*.py"))
    if not scripts:
        print(f"[experiments] no scripts found under {EXPERIMENTS_DIR}")
        return 0

    import subprocess  # noqa: PLC0415

    failed: list[str] = []
    for script in scripts:
        if args.only and script.stem not in args.only:
            continue
        cmd = [
            sys.executable,
            str(script),
            "--seed", str(args.seed),
            "--split", args.split,
        ]
        print(f"[experiments] running {script.name} …")
        result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            failed.append(script.name)
            print(f"[experiments] {script.name} exited {result.returncode}")
    if failed:
        print(f"[experiments] completed with skips/failures: {failed}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    payload = build_report(task=args.task, split=args.split, metric=args.metric)
    print(f"[report] wrote {REPORTS_DIR / 'evaluation.json'}")
    print(f"[report] wrote {REPORTS_DIR / 'leaderboard.md'}")
    print(f"[report] {payload['n_runs_total']} run(s) in registry; "
          f"locked test spent={payload['locked_test']['spent']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="naijafinsent.evaluation.runner",
        description="Run benchmarks and experiments, and assemble evaluation reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="run all available baselines/models on a split")
    bench.add_argument("--split", default="dev")
    bench.add_argument("--seed", type=int, default=0)
    bench.add_argument("--limit", type=int, default=None, help="cap items (fast smoke run)")
    bench.add_argument("--bootstrap", type=int, default=1000)
    bench.add_argument("--no-log", action="store_true", help="do not append to runs.jsonl")
    bench.set_defaults(func=_cmd_bench)

    experiments = sub.add_parser("experiments", help="run E1–E9 as far as the code allows")
    experiments.add_argument("--split", default="dev")
    experiments.add_argument("--seed", type=int, default=0)
    experiments.add_argument("--only", nargs="*", default=None, help="subset, e.g. e4_cost_vs_f1")
    experiments.set_defaults(func=_cmd_experiments)

    report = sub.add_parser("report", help="assemble the evaluation report artefacts")
    report.add_argument("--task", default="sentiment")
    report.add_argument("--split", default="dev")
    report.add_argument("--metric", default="macro_f1")
    report.set_defaults(func=_cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
