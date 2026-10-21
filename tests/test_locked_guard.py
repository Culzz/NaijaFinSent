"""Tests for the locked-test guard in :mod:`naijafinsent.evaluation.runner`.

The guard is a real deliverable, not a convention: the first evaluation is
allowed, the second is refused, and the override is only available through an
explicit, deliberately-named force flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from naijafinsent.evaluation import runner


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "locked_test_state.json"


def test_first_evaluation_runs_and_spends_the_lock(state_file: Path):
    calls: list[int] = []

    def evaluate() -> dict:
        calls.append(1)
        return {"macro_f1": 0.71}

    result = runner.evaluate_locked_once(evaluate, state_path=state_file)
    assert result == {"macro_f1": 0.71}
    assert len(calls) == 1
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["spent"] is True
    assert len(state["evaluations"]) == 1
    assert state["evaluations"][0]["forced"] is False


def test_second_evaluation_raises_without_force(state_file: Path):
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)
    with pytest.raises(runner.LockedTestError) as excinfo:
        runner.evaluate_locked_once(lambda: {"ok": 2}, state_path=state_file)
    # The message should name when the lock was spent so a reader can find it.
    assert "already been evaluated" in str(excinfo.value)

    # And the underlying evaluation must NOT have run a second time.
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state["evaluations"]) == 1


def test_second_evaluation_permitted_with_force_and_is_recorded(state_file: Path):
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)
    result = runner.evaluate_locked_once(
        lambda: {"ok": 2},
        force=True,
        reason="debugging a pipeline crash",
        state_path=state_file,
    )
    assert result == {"ok": 2}
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state["evaluations"]) == 2
    assert state["evaluations"][1]["forced"] is True
    assert state["evaluations"][1]["reason"] == "debugging a pipeline crash"
    # The history is preserved: the original evaluation is still the first entry.
    assert state["evaluations"][0]["forced"] is False


def test_force_still_appends_and_never_hides_earlier_runs(state_file: Path):
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)
    for _ in range(3):
        runner.evaluate_locked_once(lambda: {"ok": 2}, force=True, state_path=state_file)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert [e["forced"] for e in state["evaluations"]] == [False, True, True, True]
    assert len(state["evaluations"]) == 4


def test_locked_state_defaults_to_unspent_when_file_absent(tmp_path: Path):
    state = runner.locked_state(tmp_path / "absent.json")
    assert state["spent"] is False
    assert state["evaluations"] == []


def test_corrupt_state_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert runner.locked_state(bad)["spent"] is True
    # And it must refuse to run without force, even though we cannot read the file.
    with pytest.raises(runner.LockedTestError):
        runner.evaluate_locked_once(lambda: 1, state_path=bad)


def test_reset_lock_for_tests_clears_state(state_file: Path):
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)
    runner.reset_lock_for_tests(state_file)
    assert not state_file.exists()
    # Allowed again after a test-only reset.
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)


def test_force_flag_constant_is_the_documented_string():
    assert runner.FORCE_FLAG == "--force-i-know-this-breaks-the-protocol"


def test_state_file_records_git_sha_key(state_file: Path):
    runner.evaluate_locked_once(lambda: {"ok": 1}, state_path=state_file)
    entry = json.loads(state_file.read_text(encoding="utf-8"))["evaluations"][0]
    assert "git_sha" in entry
    assert entry["run_id"].startswith("locked-")
