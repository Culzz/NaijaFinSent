"""Tests for :mod:`naijafinsent.evaluation.error_analysis`.

The categoriser is a triage aid, so these tests pin the *signals we promised to
detect* (sarcasm, Pidgin, naira/macro language, abbreviations, and the
uncertain-vs-neutral boundary) rather than the exact word lists, which are
expected to grow.
"""

from __future__ import annotations

from pathlib import Path

from naijafinsent.evaluation.error_analysis import (
    ERROR_CATEGORIES,
    ErrorRecord,
    categorise_error,
    error_summary,
    export_errors_csv,
    export_errors_jsonl,
    make_error_records,
    manual_queue,
    tag_errors,
)


# ---------------------------------------------------------------------------
# Taxonomy is complete
# ---------------------------------------------------------------------------

def test_taxonomy_contains_the_required_categories():
    ids = {c.id for c in ERROR_CATEGORIES}
    for required in (
        "sarcasm",
        "mixed_sentiment",
        "naira_macro",
        "pidgin",
        "unseen_entity",
        "abbreviation",
    ):
        assert required in ids


def test_every_category_has_definition_and_confidence():
    for category in ERROR_CATEGORIES:
        assert category.definition
        assert category.heuristic_confidence in {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# Heuristic tagging on constructed examples
# ---------------------------------------------------------------------------

def test_pidgin_is_tagged():
    tags = categorise_error(
        {"text": "Wahala don land for the FX market, e don better small"},
        "negative",
        "positive",
    )
    assert "pidgin" in tags


def test_sarcasm_is_tagged_on_scare_quotes():
    tags = categorise_error(
        {"text": 'CBN says the naira is "stable" again — what a surprise'},
        "negative",
        "positive",
    )
    assert "sarcasm" in tags


def test_naira_macro_language_is_tagged():
    tags = categorise_error(
        {"text": "The CBN raised the MPR by 200 basis points to fight inflation"},
        "negative",
        "positive",
    )
    assert "naira_macro" in tags


def test_abbreviations_are_tagged():
    tags = categorise_error(
        {"text": "EPS beat, ROE up, and the NGN strengthened against the dollar"},
        "positive",
        "neutral",
    )
    assert "abbreviation" in tags


def test_mixed_sentiment_is_tagged_when_both_polarities_appear():
    tags = categorise_error(
        {"text": "Profit rose sharply but the unit posted a record loss in FX"},
        "positive",
        "negative",
    )
    assert "mixed_sentiment" in tags


def test_uncertain_neutral_confusion_is_tagged_on_that_label_pair():
    tags = categorise_error({"text": "The deal may close pending approval"}, "uncertain", "neutral")
    assert "uncertain_neutral_confusion" in tags


def test_long_document_is_tagged_above_the_threshold():
    tags = categorise_error({"text": "word " * 800}, "positive", "negative")
    assert "long_document" in tags


def test_unseen_entity_only_fires_when_metadata_says_so():
    assert "unseen_entity" not in categorise_error({"text": "GTCO reported"}, "positive", "neutral")
    assert "unseen_entity" in categorise_error(
        {"text": "NewCo Ltd reported", "unseen_entities": ["NewCo Ltd"]},
        "positive",
        "neutral",
    )


def test_neutral_text_produces_no_tags():
    tags = categorise_error({"text": "The company filed its annual report."}, "neutral", "neutral")
    assert tags == []


def test_tags_are_deduplicated_and_in_taxonomy_order():
    tags = categorise_error(
        {"text": "Wahala dey for naira as MPR rises and profit falls"},
        "negative",
        "positive",
    )
    assert len(tags) == len(set(tags))
    order = {c.id: i for i, c in enumerate(ERROR_CATEGORIES)}
    assert tags == sorted(tags, key=lambda t: order[t])


def test_rules_override_table_is_respected():
    # With a custom Pidgin list, a phrase the defaults miss is caught.
    tags = categorise_error(
        {"text": "the market just gbam us"},
        "negative",
        "positive",
        rules={"pidgin": ["gbam"]},
    )
    assert "pidgin" in tags


# ---------------------------------------------------------------------------
# Records, queue, summary
# ---------------------------------------------------------------------------

def _records() -> list[ErrorRecord]:
    gold = ["negative", "positive", "neutral", "positive"]
    pred = ["positive", "negative", "neutral", "positive"]
    samples = [
        {"item_id": "a", "text": "Wahala don land for the naira", "publisher": "punch"},
        {"item_id": "b", "text": 'The naira is "stable" — what a surprise', "publisher": "punch"},
        {"item_id": "c", "text": "nothing wrong here", "publisher": "bd"},
        {"item_id": "d", "text": "correct prediction", "publisher": "bd"},
    ]
    return make_error_records(gold, pred, samples)


def test_make_error_records_only_keeps_mispredictions():
    records = _records()
    assert [r.item_id for r in records] == ["a", "b"]  # c and d are correct


def test_tag_errors_fills_tags():
    records = tag_errors(_records())
    assert any("pidgin" in r.tags for r in records)
    assert any("sarcasm" in r.tags for r in records)


def test_error_summary_counts_are_correct():
    records = tag_errors(_records())
    summary = error_summary(records)
    assert summary["n_errors"] == 2
    assert summary["counts"]["pidgin"] == 1
    assert summary["counts"]["sarcasm"] == 1
    assert summary["untagged"] == 0
    assert len(summary["by_category"]["sarcasm"]["examples"]) == 1


def test_error_summary_untagged_counts_errors_no_rule_fired_on():
    records = [ErrorRecord(item_id="x", text="plain text", gold="a", pred="b")]
    summary = error_summary(records)
    assert summary["untagged"] == 1


def test_manual_queue_is_a_deterministic_ordering():
    gold = ["negative"] * 5
    pred = ["positive"] * 5
    samples = [{"item_id": str(i), "text": "wahala dey for naira " + str(i)} for i in range(5)]
    records = tag_errors(make_error_records(gold, pred, samples))
    a = [r.item_id for r in manual_queue(records, 3, seed=0)]
    b = [r.item_id for r in manual_queue(records, 3, seed=0)]
    assert a == b
    assert len(a) == 3


def test_manual_queue_prioritise_puts_a_category_first():
    records = [
        ErrorRecord(item_id="plain", text="long text " * 900, gold="a", pred="b",
                    tags=["long_document"]),
        ErrorRecord(item_id="sarc", text="text", gold="a", pred="b", tags=["sarcasm"]),
    ]
    queue = manual_queue(records, 2, prioritise=["sarcasm"])
    assert queue[0].item_id == "sarc"


def test_manual_queue_can_hold_100_plus_items():
    gold = ["negative"] * 120
    pred = ["positive"] * 120
    samples = [{"item_id": str(i), "text": f"wahala dey {i}"} for i in range(120)]
    records = tag_errors(make_error_records(gold, pred, samples))
    assert len(manual_queue(records, 100)) == 100


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_errors_csv_round_trips(tmp_path: Path):
    records = tag_errors(_records())
    out = export_errors_csv(records, tmp_path / "errors.csv")
    text = out.read_text(encoding="utf-8")
    assert "item_id" in text and "confirmed_tags" in text
    assert len(text.strip().splitlines()) == 3  # header + 2 errors


def test_export_errors_jsonl_keeps_full_text(tmp_path: Path):
    records = tag_errors(_records())
    out = export_errors_jsonl(records, tmp_path / "errors.jsonl")
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    first = json.loads(lines[0])
    assert first["item_id"] == "a"
    assert first["text"]  # full text, not truncated
