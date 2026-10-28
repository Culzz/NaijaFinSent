"""The extractor-measurement report exists, is shaped, and is honest.

``research/reports/extractor_metrics.json`` is committed output of
``scripts/measure_extractors.py``: per-event-type and per-entity-type
precision/recall with bootstrap CIs. These tests keep it from rotting —
they do NOT enforce target values (the numbers are supposed to be honest,
including ugly ones).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "research" / "reports" / "extractor_metrics.json"
report = json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_carries_both_measured_families():
    assert set(report["events"]) >= {
        "cbn_policy", "earnings", "dividend", "mna",
        "regulatory_sanction", "capital_raise", "fx_move",
    }
    assert {"ORG/TICKER", "REGULATOR"} <= set(report["ner"])


def test_every_cell_has_counts_and_cis():
    for section in ("events", "ner"):
        for _type, cell in report[section].items():
            assert isinstance(cell["n_gold"], int)
            assert isinstance(cell["n_predicted"], int)
            for key in ("recall", "precision"):
                if cell[key] is not None:
                    assert 0.0 <= cell[key] <= 1.0
                    ci = cell[f"{key}_ci95"]
                    assert ci is not None and ci[0] <= ci[1]
                    assert 0.0 <= ci[0] and ci[1] <= 1.0
            assert cell["n_gold"] + cell["n_predicted"] > 0, f"empty cell {_type}"


def test_the_method_is_stated_not_implied():
    note = report["ner"]["ORG/TICKER"]["note"]
    assert "surface-form" in note
    assert "_offsets_" in note or "offsets" in note


def test_event_recall_never_exceeds_the_gold_count_it_rests_on():
    # Guard against the classic lie: recall=1.0 implied meaningful, when it
    # sits on 5 gold items. The report must carry n_gold so a reader can check.
    cbn = report["events"]["cbn_policy"]
    assert cbn["n_gold"] >= 40  # 70 gold policy items in the gold set


def test_report_matches_one_item_row():
    assert report["n_items"] >= 1000
