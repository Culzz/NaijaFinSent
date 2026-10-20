"""Locked split builder with dedup-aware, leakage-proof assignments.

Builds four split *views* over one annotation pool:

* ``random``        — stratified by sentiment label and event type, seeded.
* ``source_held_out`` — one publisher is fully excluded from train and appears
  only in the held-out evaluation set.
* ``time_held_out`` — the latest period is held out (requires ``published_at``).
* ``test``          — a frozen test set, evaluated once.

Guarantees:

1. **The same item never appears in two splits.** ``verify_no_leakage`` checks
   this across every view and across canonical/duplicate pairs.
2. **Duplicates and syndicated copies stay with their canonical item.** A
   ``duplicate_groups`` map (or cluster list) forces every member into the split
   its canonical item lands in.

Determinism: all randomness draws from a seeded ``random.Random`` so two runs
with the same seed produce byte-identical assignments.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from naijafinsent.schemas import AnnotationRecord

SPLIT_NAMES: tuple[str, ...] = ("train", "dev", "test_random", "test_source", "test_time")
VIEW_NAMES: tuple[str, ...] = ("random", "source_held_out", "time_held_out", "test")
DEFAULT_SEED = 42


# --------------------------------------------------------------------------
# Dependencies for an item (minimal fields splits needs)
# --------------------------------------------------------------------------

@dataclass
class SplitItem:
    """The fields split assignment needs, decoupled from the full schema."""

    item_id: str
    publisher: str = "unknown"
    published_at: datetime | None = None
    sentiment_label: str | None = None
    event_types: tuple[str, ...] = ()
    canonical_id: str | None = None
    is_duplicate: bool = False

    @property
    def group_key(self) -> str:
        """The dedup cluster this item belongs to (itself if canonical)."""
        return self.canonical_id or self.item_id


def items_from_records(
    records: Iterable[AnnotationRecord],
    *,
    publisher_by_article: Mapping[str, str] | None = None,
    published_by_article: Mapping[str, datetime | date | str] | None = None,
    duplicate_groups: Mapping[str, str] | None = None,
) -> list[SplitItem]:
    """Build ``SplitItem``s from ``AnnotationRecord``s plus side maps.

    ``duplicate_groups`` maps ``article_id -> canonical_id``; it is applied to
    both ``item_id`` and ``article_id`` so either key resolves.
    """
    pubs = publisher_by_article or {}
    dates = published_by_article or {}
    dups = duplicate_groups or {}

    items: list[SplitItem] = []
    for record in records:
        published = _coerce_datetime(dates.get(record.article_id) or dates.get(record.item_id))
        canonical = dups.get(record.article_id) or dups.get(record.item_id)
        if canonical in ("", None):
            canonical = None
        label = None
        if record.sentiment is not None:
            label = str(getattr(record.sentiment.label, "value", record.sentiment.label))
        event_types = tuple(
            sorted(str(getattr(e.event_type, "value", e.event_type)) for e in record.events)
        )
        items.append(
            SplitItem(
                item_id=record.item_id,
                publisher=pubs.get(record.article_id, pubs.get(record.item_id, "unknown")),
                published_at=published,
                sentiment_label=label,
                event_types=event_types,
                canonical_id=canonical,
                is_duplicate=canonical is not None,
            )
        )
    return items


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Dedup-aware stratified split
# --------------------------------------------------------------------------

def _groups(items: Sequence[SplitItem]) -> dict[str, list[SplitItem]]:
    """Group items by dedup cluster key, preserving insertion order."""
    grouped: dict[str, list[SplitItem]] = defaultdict(list)
    order: list[str] = []
    for item in items:
        if item.group_key not in grouped:
            order.append(item.group_key)
        grouped[item.group_key].append(item)
    return {key: grouped[key] for key in order}


def _stratify_key(item: SplitItem) -> str:
    label = item.sentiment_label or "none"
    event = item.event_types[0] if item.event_types else "none"
    return f"{label}|{event}"


def _dedup_aware_stratified_split(
    items: Sequence[SplitItem],
    *,
    rng: random.Random,
    fractions: Mapping[str, float],
    seed: int,
) -> dict[str, list[str]]:
    """Assign whole dedup clusters to splits, stratified by cluster stratum."""
    groups = _groups(items)

    # Stratum of a cluster = stratum of its canonical (first) member.
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for key, members in groups.items():
        by_stratum[_stratify_key(members[0])].append(key)

    assignment: dict[str, str] = {}
    target_splits = list(fractions.keys())
    for _stratum, keys in by_stratum.items():
        keys = list(keys)
        rng.shuffle(keys)
        n = len(keys)
        # Compute deterministic cut points from the fractions.
        cuts: list[tuple[str, int]] = []
        remaining = n
        for i, split in enumerate(target_splits):
            if i == len(target_splits) - 1:
                take = remaining
            else:
                take = int(round(fractions[split] * n))
                take = max(0, min(take, remaining))
            cuts.append((split, take))
            remaining -= take
        idx = 0
        for split, take in cuts:
            for key in keys[idx : idx + take]:
                assignment[key] = split
            idx += take

    out: dict[str, list[str]] = {split: [] for split in target_splits}
    for key, members in groups.items():
        split = assignment.get(key, target_splits[0])
        for member in members:
            out[split].append(member.item_id)
    for split in out:
        out[split].sort()
    return out


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def build_random_view(
    items: Sequence[SplitItem],
    *,
    rng: random.Random,
    train_frac: float = 0.7,
    dev_frac: float = 0.15,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[str]]:
    """Stratified random split; train/dev from the pool, ``test_random`` held out."""
    test_frac = max(0.0, 1.0 - train_frac - dev_frac)
    return _dedup_aware_stratified_split(
        items,
        rng=rng,
        fractions={"train": train_frac, "dev": dev_frac, "test_random": test_frac},
        seed=seed,
    )


def build_source_held_out_view(
    items: Sequence[SplitItem],
    *,
    rng: random.Random,
    held_out_publisher: str,
    train_frac: float = 0.8,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[str]]:
    """One publisher is fully removed from train/dev and placed in ``test_source``."""
    heldout_items = [i for i in items if i.publisher == held_out_publisher]
    rest = [i for i in items if i.publisher != held_out_publisher]

    dev_frac = max(0.0, 1.0 - train_frac)
    inner = _dedup_aware_stratified_split(
        rest,
        rng=rng,
        fractions={"train": train_frac, "dev": dev_frac},
        seed=seed,
    )
    # Every held-out item (and its dedup cluster) goes to test_source only if
    # the whole cluster is from that publisher; clusters split across publishers
    # are excluded to keep the exclusion honest.
    heldout_ids = {i.item_id for i in heldout_items}
    clean_heldout: list[str] = []
    grouped = _groups(items)
    for key, members in grouped.items():
        member_ids = {m.item_id for m in members}
        if member_ids <= heldout_ids:
            clean_heldout.extend(member_ids)
    return {
        "train": sorted(inner.get("train", [])),
        "dev": sorted(inner.get("dev", [])),
        "test_source": sorted(clean_heldout),
    }


def build_time_held_out_view(
    items: Sequence[SplitItem],
    *,
    rng: random.Random,
    cutoff: datetime,
    train_frac: float = 0.8,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[str]]:
    """Everything at/after ``cutoff`` goes to ``test_time``; earlier items are split."""
    dated = [i for i in items if i.published_at is not None]
    late = [i for i in dated if i.published_at >= cutoff]
    early = [i for i in dated if i.published_at < cutoff]
    undated = [i for i in items if i.published_at is None]

    dev_frac = max(0.0, 1.0 - train_frac)
    inner = _dedup_aware_stratified_split(
        early + undated,
        rng=rng,
        fractions={"train": train_frac, "dev": dev_frac},
        seed=seed,
    )
    return {
        "train": sorted(inner.get("train", [])),
        "dev": sorted(inner.get("dev", [])),
        "test_time": sorted(i.item_id for i in late),
    }


def build_test_view(
    items: Sequence[SplitItem],
    *,
    rng: random.Random,
    test_frac: float = 0.2,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[str]]:
    """A frozen once-evaluated test set: ``test`` vs ``rest``."""
    return _dedup_aware_stratified_split(
        items,
        rng=rng,
        fractions={"train": 1.0 - test_frac, "dev": 0.0, "test": test_frac},
        seed=seed,
    )


# --------------------------------------------------------------------------
# Top-level builder
# --------------------------------------------------------------------------

@dataclass
class SplitBundle:
    """All four split views plus the manifest metadata."""

    views: dict[str, dict[str, list[str]]]
    items: list[SplitItem]
    seed: int
    dedup_groups: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def sizes(self) -> dict[str, dict[str, int]]:
        return {
            view: {split: len(ids) for split, ids in splits.items()}
            for view, splits in self.views.items()
        }

    def manifest(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "n_items": len(self.items),
            "n_dedup_groups": len(_groups(self.items)),
            "sizes": self.sizes(),
            "publisher_boundaries": self.metadata.get("publisher_boundaries", {}),
            "time_boundaries": self.metadata.get("time_boundaries", {}),
            "views": list(self.views),
            "split_names": list(SPLIT_NAMES),
            "frozen": True,
        }


def build_splits(
    items: Sequence[SplitItem],
    *,
    seed: int = DEFAULT_SEED,
    held_out_publisher: str | None = None,
    time_cutoff: datetime | None = None,
    train_frac: float = 0.7,
    dev_frac: float = 0.15,
    test_frac: float = 0.2,
    source_train_frac: float = 0.8,
    time_train_frac: float = 0.8,
) -> SplitBundle:
    """Build all four split views deterministically from one item pool.

    Each view draws from its own ``random.Random(seed + offset)`` so view order
    does not perturb any other view, and two runs with the same seed are
    identical.
    """
    items = list(items)
    viewed = sorted(items, key=lambda i: i.item_id)

    if held_out_publisher is None:
        held_out_publisher = _largest_publisher(viewed)
    if time_cutoff is None:
        time_cutoff = _median_date(viewed)

    views: dict[str, dict[str, list[str]]] = {}
    views["random"] = build_random_view(
        viewed,
        rng=random.Random(seed),
        train_frac=train_frac,
        dev_frac=dev_frac,
        seed=seed,
    )
    views["source_held_out"] = build_source_held_out_view(
        viewed,
        rng=random.Random(seed + 1),
        held_out_publisher=held_out_publisher,
        train_frac=source_train_frac,
        seed=seed,
    )
    views["time_held_out"] = build_time_held_out_view(
        viewed,
        rng=random.Random(seed + 2),
        cutoff=time_cutoff,
        train_frac=time_train_frac,
        seed=seed,
    )
    views["test"] = build_test_view(
        viewed,
        rng=random.Random(seed + 3),
        test_frac=test_frac,
        seed=seed,
    )

    metadata = {
        "publisher_boundaries": {"held_out_publisher": held_out_publisher},
        "time_boundaries": {"cutoff": time_cutoff.isoformat() if time_cutoff else None},
    }
    dedup_groups = {
        i.item_id: i.canonical_id for i in viewed if i.canonical_id is not None
    }
    return SplitBundle(views=views, items=viewed, seed=seed, dedup_groups=dedup_groups,
                       metadata=metadata)


def _largest_publisher(items: Sequence[SplitItem]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.publisher] += 1
    if not counts:
        return "unknown"
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _median_date(items: Sequence[SplitItem]) -> datetime:
    dates = sorted(i.published_at for i in items if i.published_at is not None)
    if not dates:
        return datetime(2100, 1, 1)
    return dates[len(dates) // 2]


# --------------------------------------------------------------------------
# Leakage verification
# --------------------------------------------------------------------------

def verify_no_leakage(splits: SplitBundle | Mapping[str, Mapping[str, Sequence[str]]]) -> list[str]:
    """Return a list of leakage problems; empty means clean.

    Checks, per view: no item id appears in two splits; and no dedup cluster is
    spread across splits (canonical and its copies must share a split).
    """
    if isinstance(splits, SplitBundle):
        views = splits.views
        dedup = splits.dedup_groups
    else:
        views = {k: dict(v) for k, v in splits.items()}
        dedup = {}

    problems: list[str] = []
    for view_name, split_map in views.items():
        seen: dict[str, str] = {}
        for split, ids in split_map.items():
            for item_id in ids:
                if item_id in seen:
                    problems.append(
                        f"[{view_name}] item {item_id!r} in both "
                        f"{seen[item_id]!r} and {split!r}"
                    )
                else:
                    seen[item_id] = split
        # Dedup cluster consistency within the view.
        cluster_splits: dict[str, set[str]] = defaultdict(set)
        for split, ids in split_map.items():
            for item_id in ids:
                canonical = dedup.get(item_id, item_id)
                cluster_splits[canonical].add(split)
        for canonical, splitset in cluster_splits.items():
            if len(splitset) > 1:
                problems.append(
                    f"[{view_name}] dedup cluster {canonical!r} spread across "
                    f"{sorted(splitset)}"
                )
    return problems


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def write_splits(
    bundle: SplitBundle,
    directory: str | Path,
) -> dict[str, Path]:
    """Write per-view JSONL assignment files plus ``splits.manifest.json``."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    for view_name, split_map in bundle.views.items():
        path = out / f"splits.{view_name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for split, ids in split_map.items():
                for item_id in ids:
                    fh.write(json.dumps({"item_id": item_id, "split": split}) + "\n")
        written[view_name] = path

    manifest_path = out / "splits.manifest.json"
    manifest_path.write_text(json.dumps(bundle.manifest(), indent=2), encoding="utf-8")
    written["manifest"] = manifest_path
    return written
