"""Tests for :mod:`naijafinsent.evaluation.registry`.

Covers logging, leaderboard ordering, the documented tie-break, and — most
importantly — that every stored run carries the attribution fields the brief
requires (model, version, task, split, seed, metrics, params, timestamp, git sha,
dataset version/hash).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from naijafinsent.evaluation import registry as R


@pytest.fixture()
def runs_file(tmp_path: Path) -> Path:
    return tmp_path / "runs.jsonl"


def _log(path: Path, model: str, value: float, **extra) -> dict:
    record = {
        "model": model,
        "version": extra.pop("version", "0.1"),
        "task": extra.pop("task", "sentiment"),
        "split": extra.pop("split", "dev"),
        "seed": extra.pop("seed", 0),
        "metrics": {"macro_f1": value, **extra.pop("metrics", {})},
        "params": extra.pop("params", {"C": 1.0}),
    }
    record.update(extra)
    return R.log_run(record, path=path)


# ---------------------------------------------------------------------------
# Logging and required fields
# ---------------------------------------------------------------------------

def test_log_run_appends_a_line(runs_file: Path):
    _log(runs_file, "tfidf", 0.61)
    _log(runs_file, "finbert", 0.70)
    lines = runs_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["model"] == "tfidf"


def test_log_run_record_contains_every_required_attribution_field(runs_file: Path):
    stored = _log(runs_file, "tfidf", 0.61, dataset_version="dev:v1")
    for field in R.REQUIRED_RUN_FIELDS:
        assert field in stored, f"missing required field {field}"
        # dataset_version may be None only if the caller explicitly passes none;
        # here it was supplied, so it must be present.
    assert stored["dataset_version"] == "dev:v1"
    assert stored["dataset_hash"] == R.dataset_hash("dev:v1")
    assert stored["timestamp"]  # non-empty
    assert stored["run_id"].startswith("run-")


def test_git_sha_is_none_or_a_string(runs_file: Path):
    stored = _log(runs_file, "tfidf", 0.5)
    assert stored["git_sha"] is None or isinstance(stored["git_sha"], str)


def test_dataset_hash_distinguishes_versions():
    assert R.dataset_hash("v1") != R.dataset_hash("v2")
    assert R.dataset_hash("v1") == R.dataset_hash("v1")
    # None hashes the sentinel, never empty.
    assert R.dataset_hash(None) == R.dataset_hash("unversioned")


def test_log_run_rejects_record_missing_required_fields(runs_file: Path):
    with pytest.raises(ValueError):
        R.log_run({"model": "x"}, path=runs_file)  # no task/split/metrics


def test_load_runs_skips_corrupt_lines(runs_file: Path):
    _log(runs_file, "a", 0.1)
    with runs_file.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
        fh.write("\n")
    _log(runs_file, "b", 0.2)
    loaded = R.load_runs(runs_file)
    assert [r["model"] for r in loaded] == ["a", "b"]


def test_load_runs_missing_file_returns_empty(tmp_path: Path):
    assert R.load_runs(tmp_path / "nope.jsonl") == []


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

def test_leaderboard_orders_by_metric_descending(runs_file: Path):
    _log(runs_file, "tfidf", 0.61)
    _log(runs_file, "finbert", 0.78)
    _log(runs_file, "distilbert", 0.70)
    table = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert [row["model"] for row in table] == ["finbert", "distilbert", "tfidf"]
    assert table[0]["rank"] == 1


def test_leaderboard_filters_by_task_and_split(runs_file: Path):
    _log(runs_file, "a", 0.9, task="sentiment", split="dev")
    _log(runs_file, "b", 0.5, task="ner", split="dev")
    _log(runs_file, "c", 0.7, task="sentiment", split="test_time")
    table = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert [row["model"] for row in table] == ["a"]


def test_leaderboard_excludes_runs_missing_the_metric(runs_file: Path):
    _log(runs_file, "a", 0.9)
    R.log_run(
        {"model": "b", "task": "sentiment", "split": "dev", "metrics": {"accuracy": 0.9}},
        path=runs_file,
    )
    table = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert [row["model"] for row in table] == ["a"]


def test_leaderboard_keeps_latest_run_per_key(runs_file: Path):
    _log(runs_file, "a", 0.5, version="1", timestamp="2024-01-01T00:00:00")
    _log(runs_file, "a", 0.7, version="1", timestamp="2024-02-01T00:00:00")
    latest = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert len(latest) == 1
    assert latest[0]["value"] == pytest.approx(0.7)
    history = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file, include_history=True)
    assert len(history) == 2


def test_leaderboard_carries_ci_when_present(runs_file: Path):
    R.log_run(
        {
            "model": "a", "task": "sentiment", "split": "dev",
            "metrics": {"macro_f1": {"value": 0.7, "ci_low": 0.65, "ci_high": 0.75}},
        },
        path=runs_file,
    )
    row = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)[0]
    assert row["value"] == pytest.approx(0.7)
    assert row["ci_low"] == pytest.approx(0.65)
    assert row["ci_high"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Tie-break (documented rule) and select_best
# ---------------------------------------------------------------------------

def test_tie_break_prefers_cheaper_model_when_f1_equal(runs_file: Path):
    _log(runs_file, "expensive", 0.80, metrics={"usd_per_1k": 12.0})
    _log(runs_file, "cheap", 0.80, metrics={"usd_per_1k": 0.01})
    table = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert table[0]["model"] == "cheap"


def test_tie_break_prefers_faster_model_when_f1_and_cost_equal(runs_file: Path):
    _log(runs_file, "slow", 0.80, metrics={"usd_per_1k": 0.0, "per_item_mean_ms": 900.0})
    _log(runs_file, "fast", 0.80, metrics={"usd_per_1k": 0.0, "per_item_mean_ms": 3.0})
    table = R.leaderboard("sentiment", "macro_f1", "dev", path=runs_file)
    assert table[0]["model"] == "fast"


def test_select_best_returns_highest_f1(runs_file: Path):
    _log(runs_file, "a", 0.61)
    _log(runs_file, "b", 0.78)
    best = R.select_best("sentiment", "macro_f1", "dev", path=runs_file)
    assert best is not None and best["model"] == "b"
    assert "tie_break" in best and "selection_rule" in best


def test_select_best_respects_min_value_floor(runs_file: Path):
    _log(runs_file, "a", 0.61)
    _log(runs_file, "b", 0.40)
    assert R.select_best("sentiment", "macro_f1", "dev", path=runs_file, min_value=0.9) is None
    assert R.select_best(
        "sentiment", "macro_f1", "dev", path=runs_file, min_value=0.5
    )["model"] == "a"


def test_select_best_empty_registry_returns_none(runs_file: Path):
    assert R.select_best("sentiment", "macro_f1", "dev", path=runs_file) is None
