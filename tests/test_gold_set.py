"""Guards for the committed gold set (data/annotation/gold/gold_set.jsonl).

These tests turn the gold set from a folder of claims into an enforced
contract: size floor, label space, uniqueness, split integrity, marker
coverage of the hard Nigerian cases, and the honesty contract (annotator
provenance is machine-assisted and declared everywhere).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from naijafinsent.annotation.agreement import cohens_kappa
from naijafinsent.constants import SENTIMENT_LABELS

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "data" / "annotation" / "gold" / "gold_set.jsonl"
MANIFEST_PATH = ROOT / "data" / "annotation" / "gold" / "gold_manifest.json"

items = [json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_gold_set_exists_and_clears_the_size_floor():
    assert len(items) >= 1000, "the roadmap floor is 1,000 labelled items"


def test_every_item_is_in_the_declared_label_space():
    for it in items:
        assert it["sentiment"]["label"] in SENTIMENT_LABELS


def test_ids_and_texts_are_unique():
    ids = [it["item_id"] for it in items]
    texts = [it["text"] for it in items]
    assert len(ids) == len(set(ids)), "item ids must be unique"
    assert len(texts) == len(set(texts)), "exact duplicate texts must be dropped"


def test_manifest_counts_match_the_file():
    assert manifest["n_items"] == len(items)
    labels = Counter(it["sentiment"]["label"] for it in items)
    assert manifest["labels"] == dict(labels)


def test_manifest_is_honest_about_annotator_provenance():
    assert manifest["annotator"].startswith("model-assisted")
    assert manifest["inter_annotator_kappa"] is None
    # Every single label must carry the machine-assisted marker.
    for it in items:
        assert it["sentiment"]["annotator"] == "model-assisted-glm"
        assert it["sentiment"]["model_prelabel"] is True


def test_flat_splits_cover_every_item_exactly_once():
    counts = Counter(it["split"] for it in items)
    assert set(counts) == {"train", "dev", "test_random"}
    assert sum(counts.values()) == len(items)
    assert counts["train"] == max(counts.values()), "train must dominate the flat split"


def test_split_view_sizes_are_recorded():
    sizes = manifest["split_view_sizes"]
    for view in ("random", "source_held_out", "time_held_out", "test"):
        assert view in sizes, f"missing locked view {view}"
    assert "test_source" in sizes["source_held_out"]
    assert "test_time" in sizes["time_held_out"]
    assert sizes["random"]["test_random"] > 0


def test_hard_nigerian_markers_are_covered():
    markers = Counter(m for it in items for m in it["markers"])
    for marker, floor in (
        ("pidgin", 20),
        ("naira_symbol", 20),
        ("naira_abbrev", 20),
        ("trn_bn_abbrev", 6),
        ("headline_fragment", 40),
        ("ticker_collision", 4),
        ("entity_paired", 4),
    ):
        assert markers[marker] >= floor, f"marker {marker} under-covered: {markers[marker]}"


def test_all_four_labels_are_present_in_volume():
    labels = Counter(it["sentiment"]["label"] for it in items)
    for label in SENTIMENT_LABELS:
        assert labels[label] >= 50, f"label {label} under-represented: {labels[label]}"


def test_kappa_helper_behaves_on_gold_like_streams():
    gold = [it["sentiment"]["label"] for it in items]
    assert cohens_kappa(gold, gold) == pytest.approx(1.0)
    shuffled = gold[::-1]
    kappa = cohens_kappa(gold, shuffled)
    assert -1.0 <= kappa <= 1.0


def test_synthetic_items_never_pretend_to_be_organic():
    for it in items:
        if it["source"] != "curated":
            assert it["is_synthetic"] is True
