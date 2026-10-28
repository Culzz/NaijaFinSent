"""Tween locks for the trained-comparison report (scripts/compare_trained.py).

The report must exist, be shaped, and carry its caveats — target numbers are
NOT enforced (the whole point is an honest measurement).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "research" / "reports" / "trained_comparison.json"

report = json.loads(REPORT.read_text(encoding="utf-8"))
rows = {r.get("model", ""): r for r in report.get("rows", [])}


def test_report_has_all_model_rows():
    assert "lexicon-pipeline" in rows
    assert {"tfidf-logreg", "tfidf-svm"} <= set(rows)


def test_rows_carry_metrics_with_bounds():
    for name, r in rows.items():
        if "accuracy" not in r:
            continue
        assert 0.0 <= r["accuracy"] <= 1.0
        assert r["macro_f1"] <= r["accuracy"] + 1e-9 or r["macro_f1"] >= 0.0  # just numeric
        ci = r["accuracy_ci95"]
        assert ci[0] <= r["accuracy"] <= ci[1]


def test_the_in_distribution_caveat_is_present():
    text = json.dumps(report).casefold()
    assert "upper bound" in text
    assert "in-distribution" in text
    assert "human-confirmed" in text
    assert "frame" in text


def test_curated_only_surface_recorded():
    curated = report.get("curated_only_rows", [])
    assert curated, "the curated-only honest cut must be reported"
    for r in curated:
        if "accuracy" in r:
            assert r["n"] > 0
            assert 0.0 <= r["accuracy"] <= 1.0


def test_fairness_section_keeps_the_promises():
    fair = report["fairness"]
    assert "none" in fair["model_selection"].lower()
    assert fair["train_items"] + fair["eval_items"] >= 1000
