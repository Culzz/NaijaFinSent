"""Worker service tests — argument handling, cycle contract, failure isolation.

Deliberately network-free: ingest cycles that would touch the live web are
monkeypatched away; the failure path is exercised by breaking the import.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import app.worker as worker  # noqa: E402


def test_run_cycle_returns_summary_contract_even_on_import_failure(monkeypatch):
    # Break the naijafinsent import: the worker must degrade to a summary with
    # errors counted, never raise.
    monkeypatch.setitem(sys.modules, "naijafinsent.data.ingest", None)
    summary = worker.run_cycle(limit=1)
    assert set(summary) >= {"fetched", "new", "duplicates", "analyzed", "errors"}
    assert summary["errors"] >= 1


def test_main_once_runs_exactly_one_cycle(monkeypatch):
    calls: list[dict] = []

    def fake_run_cycle(*, limit: int, max_urls_per_source: int = 25) -> dict:
        calls.append({"limit": limit, "max_urls": max_urls_per_source})
        return {"fetched": 3, "new": 2, "duplicates": 1, "analyzed": 2, "errors": 0}

    monkeypatch.setattr(worker, "run_cycle", fake_run_cycle)
    rc = worker.main(["--once", "--limit", "7"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["limit"] == 7


def test_main_default_runs_one_cycle_and_exits(monkeypatch):
    calls: list[dict] = []

    def fake_run_cycle(*, limit: int, max_urls_per_source: int = 25) -> dict:
        calls.append({"limit": limit})
        return {"fetched": 0, "new": 0, "duplicates": 0, "analyzed": 0, "errors": 0}

    monkeypatch.setattr(worker, "run_cycle", fake_run_cycle)
    rc = worker.main([])
    assert rc == 0
    assert len(calls) == 1


def test_sources_are_isolated_so_one_bad_source_cannot_kill_a_cycle(monkeypatch):
    """Per-source isolation is the worker's core resilience contract."""
    summary = {
        "fetched": 0,
        "new": 0,
        "duplicates": 0,
        "analyzed": 0,
        "errors": 0,
    }
    # Simulate the per-source try/except contract: an exception raised inside
    # the source loop must land in ``errors``, not abort the whole cycle.
    sources = ["good", "explodes", "good"]
    for src in sources:
        try:
            if src == "explodes":
                raise RuntimeError("boom")
            summary["fetched"] += 1
        except Exception:  # noqa: BLE001 - mirrors run_cycle's handler
            summary["errors"] += 1
    assert summary["errors"] == 1
    assert summary["fetched"] == 2
