"""Tests for ``naijafinsent.annotation.splits``."""

from __future__ import annotations

from datetime import datetime

from naijafinsent.annotation.splits import (
    SplitItem,
    build_splits,
    verify_no_leakage,
    write_splits,
)

# --------------------------------------------------------------------------
# Fixture builder
# --------------------------------------------------------------------------

PUBLISHERS = ["businessday", "nairametrics", "punch", "premiumtimes"]
LABELS = ["positive", "negative", "neutral", "uncertain"]


def _make_items(n: int = 60) -> list[SplitItem]:
    items: list[SplitItem] = []
    for i in range(n):
        publisher = PUBLISHERS[i % len(PUBLISHERS)]
        published = datetime(2026, 1 + (i % 12), 1 + (i % 27))
        items.append(
            SplitItem(
                item_id=f"item_{i:03d}",
                publisher=publisher,
                published_at=published,
                sentiment_label=LABELS[i % len(LABELS)],
                event_types=(("earnings",) if i % 3 == 0 else ("dividend",)),
            )
        )
    return items


def _with_duplicates(items: list[SplitItem]) -> list[SplitItem]:
    """Add a duplicate of item_000 and a syndicated copy of item_001."""
    extra = [
        SplitItem(item_id="dup_of_000", publisher="businessday", canonical_id="item_000"),
        SplitItem(item_id="dup_of_001", publisher="nairametrics", canonical_id="item_001"),
    ]
    return items + extra


# --------------------------------------------------------------------------
# No leakage
# --------------------------------------------------------------------------

def test_no_item_leakage_in_any_view() -> None:
    items = _with_duplicates(_make_items(60))
    bundle = build_splits(items, seed=42)
    problems = verify_no_leakage(bundle)
    assert problems == [], problems


def test_every_item_assigned_exactly_once_per_view() -> None:
    items = _with_duplicates(_make_items(60))
    bundle = build_splits(items, seed=42)
    all_ids = {i.item_id for i in items}
    for view_name, split_map in bundle.views.items():
        seen = [iid for ids in split_map.values() for iid in ids]
        assert len(seen) == len(set(seen)), f"{view_name} has duplicate assignments"
        # every item appears somewhere in the view
        assert set(seen) == all_ids, f"{view_name} missing items"


# --------------------------------------------------------------------------
# Duplicates stay with canonical
# --------------------------------------------------------------------------

def test_duplicate_groups_stay_together() -> None:
    items = _with_duplicates(_make_items(60))
    bundle = build_splits(items, seed=42)
    for view_name, split_map in bundle.views.items():
        split_of: dict[str, str] = {}
        for split, ids in split_map.items():
            for iid in ids:
                split_of[iid] = split
        assert split_of["dup_of_000"] == split_of["item_000"], view_name
        assert split_of["dup_of_001"] == split_of["item_001"], view_name


# --------------------------------------------------------------------------
# Source held out
# --------------------------------------------------------------------------

def test_source_held_out_excludes_publisher_from_train() -> None:
    items = _make_items(60)
    bundle = build_splits(items, seed=42, held_out_publisher="businessday")
    view = bundle.views["source_held_out"]
    pub_of = {i.item_id: i.publisher for i in items}

    train_dev = set(view["train"]) | set(view["dev"])
    assert train_dev, "train/dev should not be empty"
    for iid in train_dev:
        assert pub_of[iid] != "businessday"

    # every businessday item is in the held-out set
    bd_ids = {i.item_id for i in items if i.publisher == "businessday"}
    assert bd_ids, "fixture should have businessday items"
    assert bd_ids <= set(view["test_source"])


# --------------------------------------------------------------------------
# Time held out
# --------------------------------------------------------------------------

def test_time_held_out_takes_latest_items() -> None:
    items = _make_items(60)
    cutoff = datetime(2026, 7, 1)
    bundle = build_splits(items, seed=42, time_cutoff=cutoff)
    view = bundle.views["time_held_out"]
    date_of = {i.item_id: i.published_at for i in items}

    for iid in view["test_time"]:
        assert date_of[iid] is not None
        assert date_of[iid] >= cutoff
    # no late item leaked into train/dev
    for iid in set(view["train"]) | set(view["dev"]):
        assert date_of[iid] < cutoff


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def test_determinism_same_seed() -> None:
    items = _with_duplicates(_make_items(60))
    b1 = build_splits(items, seed=123)
    b2 = build_splits(items, seed=123)
    assert b1.views == b2.views
    assert b1.manifest() == b2.manifest()


def test_different_seed_changes_assignment() -> None:
    items = _make_items(60)
    b1 = build_splits(items, seed=1)
    b2 = build_splits(items, seed=2)
    assert b1.views["random"] != b2.views["random"]


def test_manifest_records_boundaries() -> None:
    items = _make_items(60)
    bundle = build_splits(items, seed=42, held_out_publisher="punch")
    manifest = bundle.manifest()
    assert manifest["seed"] == 42
    assert manifest["publisher_boundaries"]["held_out_publisher"] == "punch"
    assert manifest["time_boundaries"]["cutoff"] is not None
    assert manifest["n_items"] == 60


def test_write_splits_outputs(tmp_path) -> None:
    items = _make_items(40)
    bundle = build_splits(items, seed=42)
    written = write_splits(bundle, tmp_path)
    assert (tmp_path / "splits.manifest.json").exists()
    assert (tmp_path / "splits.random.jsonl").exists()
    assert "manifest" in written


# --------------------------------------------------------------------------
# Leakage detector actually detects leakage
# --------------------------------------------------------------------------

def test_leakage_detector_flags_duplicate_across_splits() -> None:
    fake_views = {
        "random": {
            "train": ["a", "b"],
            "dev": ["a"],  # 'a' duplicated
            "test_random": [],
        }
    }
    problems = verify_no_leakage(fake_views)
    assert any("both" in p for p in problems)


def test_leakage_detector_flags_split_dedup_cluster() -> None:
    from naijafinsent.annotation.splits import SplitBundle

    bundle = SplitBundle(
        views={"random": {"train": ["canon"], "dev": ["copy"], "test_random": []}},
        items=[],
        seed=1,
        dedup_groups={"copy": "canon"},
    )
    problems = verify_no_leakage(bundle)
    assert any("dedup cluster" in p for p in problems)
