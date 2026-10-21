"""Tests for :mod:`naijafinsent.evaluation.slices`.

The point of these tests is that slice *assignment* and slice *counts* are right:
a per-slice metric is only interpretable if the items it was computed over are the
items you think they are.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from naijafinsent.evaluation import metrics as M
from naijafinsent.evaluation import slices as S


def _samples() -> list[dict]:
    return [
        {"item_id": "1", "publisher": "BusinessDay", "topic": "banking",
         "text": "x" * 100, "published_at": "2024-01-05"},
        {"item_id": "2", "publisher": "punch", "topic": "oil_and_gas",
         "text": "y" * 800, "published_at": "2024-02-10"},
        {"item_id": "3", "publisher": "Punch", "topic": "banking",
         "text": "z" * 2000, "published_at": "2024-01-20"},
        {"item_id": "4", "publisher": "Nairametrics", "topic": "telecoms",
         "text": "w" * 5000, "published_at": datetime(2023, 12, 1)},
    ]


# ---------------------------------------------------------------------------
# Key functions
# ---------------------------------------------------------------------------

def test_publisher_key_is_case_insensitive_and_merges_variants():
    buckets = S.slice_by(_samples(), S.publisher_key)
    assert set(buckets) == {"businessday", "nairametrics", "punch"}
    assert buckets["punch"] == [1, 2]  # "punch" and "Punch" collapse


def test_topic_key_takes_first_of_a_list():
    sample = {"topic": ["oil_and_gas", "banking"]}
    assert S.topic_key(sample) == "oil_and_gas"


def test_length_bucket_boundaries():
    assert S.length_bucket(0) == "short:<600"
    assert S.length_bucket(599) == "short:<600"
    assert S.length_bucket(600) == "medium:600-1500"
    assert S.length_bucket(1499) == "medium:600-1500"
    assert S.length_bucket(1500) == "long:1500-3000"
    assert S.length_bucket(3000) == "very_long:>3000"


def test_length_bucket_key_uses_text():
    buckets = S.slice_by(_samples(), S.length_bucket_key)
    assert buckets["short:<600"] == [0]
    assert buckets["medium:600-1500"] == [1]
    assert buckets["long:1500-3000"] == [2]
    assert buckets["very_long:>3000"] == [3]


def test_period_key_month_and_year():
    samples = _samples()
    assert S.period_key(samples[0]) == "2024-01"
    assert S.period_key(samples[3], granularity="year") == "2023"
    assert S.period_key(samples[3]) == "2023-12"


def test_period_key_accepts_datetime_and_missing():
    assert S.period_key({"published_at": datetime(2025, 6, 30, 12, 0)}) == "2025-06"
    assert S.period_key({"text": "no date here"}) is None


def test_slice_by_can_keep_missing_keys_under_sentinel():
    samples = [{"publisher": "a"}, {"text": "no publisher"}]
    kept = S.slice_by(samples, S.publisher_key, drop_missing=False)
    assert kept["__missing__"] == [1]
    dropped = S.slice_by(samples, S.publisher_key, drop_missing=True)
    assert "__missing__" not in dropped


# ---------------------------------------------------------------------------
# slice_report
# ---------------------------------------------------------------------------

def test_slice_report_counts_are_correct_per_bucket():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]

    report = S.slice_report(pred, gold, samples, ["publisher"], n_bootstrap=50, min_size=1)
    publishers = report["publisher"]
    assert publishers["punch"]["count"] == 2
    assert publishers["businessday"]["count"] == 1
    # punch items are indices 1 (negative->neutral, wrong) and 2 (correct):
    # macro over all four labels = 2/4 = 0.5
    assert publishers["punch"]["metric"] == pytest.approx(0.5)
    assert report["__meta__"]["n_items"] == 4


def test_slice_report_metrics_match_manual_computation():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    report = S.slice_report(pred, gold, samples, ["length"], n_bootstrap=50, min_size=1)
    # The "long" bucket is exactly item 2, which is correct -> macro F1 = 1.0
    assert report["length"]["long:1500-3000"]["metric"] == pytest.approx(1.0)


def test_slice_report_flags_low_support():
    samples = _samples()
    gold = ["positive"] * 4
    pred = list(gold)
    report = S.slice_report(pred, gold, samples, ["publisher"], min_size=3)
    # every publisher bucket is smaller than 3
    for bucket in report["publisher"].values():
        assert bucket["low_support"] is True


def test_slice_report_includes_ci_when_enough_items():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    report = S.slice_report(pred, gold, samples, ["publisher"], n_bootstrap=40, min_size=1)
    punch = report["publisher"]["punch"]
    assert punch["ci_low"] is not None and punch["ci_high"] is not None
    assert punch["ci_low"] <= punch["metric"] <= punch["ci_high"]


def test_slice_report_all_builtin_keys():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    report = S.slice_report(pred, gold, samples, n_bootstrap=30, min_size=1)
    for key in ("publisher", "topic", "length", "period"):
        assert key in report
    assert report["period"]["2024-01"]["count"] == 2


def test_slice_report_rejects_unaligned_inputs():
    with pytest.raises(ValueError):
        S.slice_report(["a"], ["a", "b"], _samples())


def test_slice_report_unknown_builtin_raises():
    with pytest.raises(ValueError):
        S.slice_report(["a"], ["a"], _samples()[:1], ["nonsense"])


def test_slice_report_is_deterministic_given_seed():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    a = S.slice_report(pred, gold, samples, ["publisher"], n_bootstrap=40, seed=5, min_size=1)
    b = S.slice_report(pred, gold, samples, ["publisher"], n_bootstrap=40, seed=5, min_size=1)
    assert a == b


# ---------------------------------------------------------------------------
# drift_curve
# ---------------------------------------------------------------------------

def test_drift_curve_is_sorted_and_counts_items():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    points = S.drift_curve(
        samples, pred, gold, S.period_key, M.macro_f1_metric(), n_bootstrap=20, min_size=1
    )
    assert [p["period"] for p in points] == ["2023-12", "2024-01", "2024-02"]
    assert points[1]["count"] == 2
    assert points[0]["count"] == 1
    # 2023-12 is item 3, correct -> F1 1.0
    assert points[0]["metric"] == pytest.approx(1.0)


def test_drift_curve_single_item_period_has_no_ci():
    samples = _samples()
    gold = ["positive", "negative", "neutral", "uncertain"]
    pred = ["positive", "neutral", "neutral", "uncertain"]
    points = S.drift_curve(
        samples, pred, gold, S.period_key, M.macro_f1_metric(), n_bootstrap=20, min_size=1
    )
    single = [p for p in points if p["count"] == 1][0]
    assert single["ci_low"] is None and single["ci_high"] is None


def test_drift_curve_custom_period_key():
    samples = _samples()
    gold = ["positive"] * 4
    pred = list(gold)
    points = S.drift_curve(
        samples, pred, gold, lambda s: S.period_key(s, granularity="year"),
        M.macro_f1_metric(), n_bootstrap=20, min_size=1,
    )
    assert [p["period"] for p in points] == ["2023", "2024"]
    assert points[1]["count"] == 3
