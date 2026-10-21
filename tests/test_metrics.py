"""Tests for :mod:`naijafinsent.evaluation.metrics`.

Every numeric expectation here is either hand-computed (and the arithmetic shown
in a comment) or a property the metric must satisfy by construction. Where a
value is compared we allow a tiny tolerance because F1 goes through float
division.
"""

from __future__ import annotations

import numpy as np
import pytest

from naijafinsent.evaluation import metrics as M

TOL = 1e-9


# ---------------------------------------------------------------------------
# Classification: macro-F1 against hand-computed values
# ---------------------------------------------------------------------------

def test_macro_f1_hand_computed_three_classes():
    # Gold:  [pos, neg, neg]
    # Pred:  [pos, pos, neg]
    # positive: tp=1 fp=1 fn=0 -> P=0.5 R=1.0 F1=2*.5*1/1.5=0.6666...
    # negative: tp=1 fp=0 fn=1 -> P=1.0 R=0.5 F1=2*1*.5/1.5=0.6666...
    # neutral:  tp=0 fp=0 fn=0 -> F1=0.0
    # macro = (0.6667 + 0.6667 + 0.0) / 3
    y_true = ["positive", "negative", "negative"]
    y_pred = ["positive", "positive", "negative"]
    expected = (2 / 3 + 2 / 3 + 0.0) / 3
    assert M.macro_f1(y_true, y_pred) == pytest.approx(expected, abs=1e-9)


def test_macro_f1_perfect_is_one():
    y = ["positive", "negative", "neutral", "uncertain"]
    assert M.macro_f1(y, list(y)) == pytest.approx(1.0)


def test_macro_f1_declared_labels_penalise_absent_class():
    # A label declared but never used should drag the macro average down: this is
    # the documented behaviour, not an accident.
    y_true = ["positive", "positive"]
    y_pred = ["positive", "positive"]
    without = M.macro_f1(y_true, y_pred, labels=["positive"])
    with_neutral = M.macro_f1(y_true, y_pred, labels=["positive", "neutral"])
    assert without == pytest.approx(1.0)
    assert with_neutral == pytest.approx(0.5)


def test_confusion_matrix_counts_and_order():
    y_true = ["a", "a", "b", "b"]
    y_pred = ["a", "b", "b", "b"]
    matrix, labels = M.confusion_matrix(y_true, y_pred)
    assert labels == ["a", "b"]
    assert matrix.tolist() == [[1, 1], [0, 2]]


def test_confusion_matrix_rejects_unknown_label_when_declared():
    with pytest.raises(ValueError):
        M.confusion_matrix(["a"], ["z"], labels=["a", "b"])


def test_accuracy_and_length_mismatch():
    assert M.accuracy(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        M.accuracy(["a"], ["a", "b"])


def test_per_class_prf_support_and_predicted_counts():
    prf = M.per_class_prf(["a", "a", "b"], ["a", "b", "b"], labels=["a", "b"])
    assert prf["a"]["support"] == 2 and prf["a"]["predicted"] == 1
    assert prf["a"]["tp"] == 1
    assert prf["b"]["support"] == 1 and prf["b"]["predicted"] == 2


def test_micro_f1_equals_accuracy_for_single_label():
    y_true = ["a", "b", "c", "a"]
    y_pred = ["a", "c", "c", "a"]
    assert M.micro_f1(y_true, y_pred) == pytest.approx(M.accuracy(y_true, y_pred))


# ---------------------------------------------------------------------------
# NER: exact vs partial
# ---------------------------------------------------------------------------

def test_entity_level_f1_exact_match():
    gold = [[("ORG", "Dangote Cement"), ("REGULATOR", "CBN")]]
    pred = [[("ORG", "Dangote Cement"), ("REGULATOR", "CBN")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    micro = out["exact"]["micro"]
    assert micro["precision"] == pytest.approx(1.0)
    assert micro["recall"] == pytest.approx(1.0)
    assert micro["f1"] == pytest.approx(1.0)


def test_entity_level_f1_surface_normalisation_is_case_and_space_insensitive():
    gold = [[("ORG", "Dangote  Cement")]]
    pred = [[("ORG", "dangote cement")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    assert out["exact"]["micro"]["f1"] == pytest.approx(1.0)


def test_entity_level_f1_partial_is_not_a_match():
    # Predicted "CBN" vs gold "Central Bank of Nigeria" — same type, overlapping
    # semantics, but not an exact surface match. It must count as fp + fn and be
    # reported in partial_matches.
    gold = [[("REGULATOR", "Central Bank of Nigeria")]]
    pred = [[("REGULATOR", "CBN")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    assert out["exact"]["micro"]["f1"] == pytest.approx(0.0)
    assert out["exact"]["partial_matches"] == 0  # neither is a substring of the other


def test_entity_level_f1_partial_substring_is_counted():
    gold = [[("MONEY", "N5 billion")]]
    pred = [[("MONEY", "N5 bill")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    assert out["exact"]["micro"]["f1"] == pytest.approx(0.0)
    assert out["exact"]["partial_matches"] == 1


def test_entity_level_f1_per_type_breakdown():
    gold = [[("ORG", "GTCO"), ("TICKER", "GTCO")]]
    pred = [[("ORG", "GTCO")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    per_type = out["exact"]["per_type"]
    assert per_type["ORG"]["f1"] == pytest.approx(1.0)
    assert per_type["TICKER"]["f1"] == pytest.approx(0.0)


def test_entity_level_f1_accepts_offset_triples():
    gold = [[(0, 3, "ORG")]]
    pred = [[(0, 3, "ORG")]]
    out = M.entity_level_f1(gold, pred, use_seqeval=False)
    assert out["exact"]["micro"]["f1"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Events: multi-label
# ---------------------------------------------------------------------------

def test_multi_label_f1_perfect_and_partial():
    gold = [["earnings"], ["dividend", "mna"]]
    pred = [["earnings"], ["dividend"]]
    out = M.multi_label_f1(gold, pred)
    # earnings: tp=1 fp=0 fn=0 -> F1=1; dividend same; mna: fn=1 -> F1=0
    assert out["per_class"]["earnings"]["f1"] == pytest.approx(1.0)
    assert out["per_class"]["mna"]["f1"] == pytest.approx(0.0)
    # micro: tp=2, fp=0, fn=1 -> P=1, R=2/3, F1=0.8
    assert out["micro"]["f1"] == pytest.approx(0.8)


def test_multi_label_f1_accepts_dense_matrix():
    labels = ["earnings", "dividend"]
    matrix = np.array([[1, 0], [0, 1]])
    out = M.multi_label_f1(matrix, matrix, labels=labels)
    assert out["micro"]["f1"] == pytest.approx(1.0)


def test_micro_and_macro_differ_on_imbalanced_labels():
    gold = [["earnings"]] * 10 + [["oil_energy"]]
    pred = [["earnings"]] * 10  # misses oil_energy entirely
    out = M.multi_label_f1(gold, pred, labels=["earnings", "oil_energy"])
    assert out["micro"]["f1"] > out["macro"]["f1"]


# ---------------------------------------------------------------------------
# Calibration: ECE / MCE / Brier
# ---------------------------------------------------------------------------

def test_ece_zero_when_perfectly_calibrated_by_construction():
    # Two documents, each predicted with confidence 1.0 and both correct.
    probs = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    y = ["positive", "negative"]
    assert M.expected_calibration_error(y, probs) == pytest.approx(0.0)
    assert M.maximum_calibration_error(y, probs) == pytest.approx(0.0)
    assert M.brier_score(y, probs) == pytest.approx(0.0)


def test_ece_positive_when_overconfident_and_wrong():
    # One document predicted positive @0.9 but actually negative.
    probs = [[0.9, 0.05, 0.03, 0.02]]
    y = ["negative"]
    ece = M.expected_calibration_error(y, probs)
    # bin [0.9, 1.0]: accuracy 0, mean conf 0.9 -> |0-0.9| * 1.0 = 0.9
    assert ece == pytest.approx(0.9)
    assert M.maximum_calibration_error(y, probs) == pytest.approx(0.9)


def test_brier_score_known_value():
    # Gold negative (one-hot [0,1,0,0]); p = [0.9,0.05,0.03,0.02]
    # squared error = 0.81 + (0.05-1)^2 + 0.0009 + 0.0004 = 0.81+0.9025+0.0013
    probs = [[0.9, 0.05, 0.03, 0.02]]
    expected = 0.9**2 + (0.05 - 1.0) ** 2 + 0.03**2 + 0.02**2
    assert M.brier_score(["negative"], probs) == pytest.approx(expected)


def test_ece_requires_matching_columns():
    with pytest.raises(ValueError):
        M.expected_calibration_error(["positive"], [[0.5, 0.5]])


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

def _toy_data(n: int = 60) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(7)
    labels = list(M.DEFAULT_LABELS)
    gold = [labels[i] for i in rng.integers(0, len(labels), size=n)]
    # 80% agreement with gold
    pred = [g if rng.random() < 0.8 else labels[(labels.index(g) + 1) % len(labels)] for g in gold]
    return gold, pred


def test_bootstrap_ci_is_deterministic_given_a_seed():
    gold, pred = _toy_data()
    fn = M.macro_f1_metric()
    a = M.bootstrap_ci(fn, gold, pred, n=200, seed=123)
    b = M.bootstrap_ci(fn, gold, pred, n=200, seed=123)
    assert a == b


def test_bootstrap_ci_differs_with_different_seed_but_brackets_point():
    gold, pred = _toy_data()
    fn = M.macro_f1_metric()
    a = M.bootstrap_ci(fn, gold, pred, n=200, seed=1)
    b = M.bootstrap_ci(fn, gold, pred, n=200, seed=2)
    assert a != b
    for result in (a, b):
        assert result["low"] <= result["point"] <= result["high"]


def test_bootstrap_ci_point_equals_metric_on_full_data():
    gold, pred = _toy_data()
    fn = M.macro_f1_metric()
    ci = M.bootstrap_ci(fn, gold, pred, n=100, seed=0)
    assert ci["point"] == pytest.approx(M.macro_f1(gold, pred))


def test_bootstrap_ci_rejects_degenerate_params():
    gold, pred = _toy_data(5)
    with pytest.raises(ValueError):
        M.bootstrap_ci(M.macro_f1_metric(), gold, pred, n=1)
    with pytest.raises(ValueError):
        M.bootstrap_ci(M.macro_f1_metric(), gold, pred, n=10, alpha=1.5)


# ---------------------------------------------------------------------------
# Paired bootstrap and McNemar
# ---------------------------------------------------------------------------

def test_paired_bootstrap_identical_models_not_significant():
    gold, pred = _toy_data()
    out = M.paired_bootstrap_test(gold, pred, list(pred), M.macro_f1_metric(), n=300, seed=0)
    assert out["observed_delta"] == pytest.approx(0.0)
    assert out["p_value"] >= 0.05
    assert out["significant_at_0.05"] is False


def test_paired_bootstrap_clearly_better_model_significant():
    gold, _ = _toy_data(120)
    perfect = list(gold)
    # A model that is right only 50% of the time.
    labels = list(M.DEFAULT_LABELS)
    rng = np.random.default_rng(0)
    bad = [
        g if rng.random() < 0.5 else labels[(labels.index(g) + 2) % len(labels)]
        for g in gold
    ]
    out = M.paired_bootstrap_test(gold, perfect, bad, M.macro_f1_metric(), n=300, seed=0)
    assert out["observed_delta"] > 0
    assert out["p_value"] < 0.05
    assert out["significant_at_0.05"] is True


def test_mcnemar_identical_models_is_non_significant():
    gold, pred = _toy_data()
    out = M.mcnemar_test(gold, pred, list(pred))
    assert out["n_discordant"] == 0
    assert out["p_value"] == pytest.approx(1.0)
    assert out["significant_at_0.05"] is False


def test_mcnemar_clearly_better_model_is_significant():
    # Hand-built: model B is wrong on 30 items where A is right, and A is wrong on
    # 0 where B is right -> b=0, c=30 -> chi2 = (30-1)^2/30 = 28.03, p ~ 1.2e-7.
    gold = ["positive"] * 30 + ["negative"] * 30
    a = list(gold)                                   # perfect
    b = ["negative"] * 30 + ["negative"] * 30        # wrong on the 30 positives
    out = M.mcnemar_test(gold, a, b)
    assert out["b"] == 0 and out["c"] == 30
    assert out["p_value"] < 0.001
    assert out["significant_at_0.05"] is True


def test_mcnemar_symmetric_disagreement_not_significant():
    gold = ["positive", "negative"]
    a = ["positive", "positive"]  # right, wrong
    b = ["negative", "negative"]  # wrong, right
    out = M.mcnemar_test(gold, a, b, continuity_correction=False)
    assert out["b"] == 1 and out["c"] == 1
    assert out["p_value"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Determinism across the package
# ---------------------------------------------------------------------------

def test_metrics_are_deterministic_across_repeated_calls():
    gold, pred = _toy_data()
    first = M.classification_report(gold, pred)
    second = M.classification_report(gold, pred)
    assert first == second
