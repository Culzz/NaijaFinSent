"""Build the committed gold set for the NaijaFinSent evaluation gates.

What this produces (all committed under ``data/annotation/gold/``):

* ``gold_set.jsonl``   — 1,000+ labelled Nigerian financial sentences.
* ``gold_manifest.json`` — counts (label / marker / family / split), the Cohen's
  kappa between the LLM-assisted labels and the lexicon system, and the locked
  split sizes stated plainly.

Honesty contract (also stated in the gold README):

1. Every label carries ``annotator="model-assisted-glm"`` and
   ``model_prelabel: true`` — an LLM-assisted pass produced the labels. **No
   human has confirmed any label yet.** The kappa reported by the gate is the
   chance-corrected agreement between the assisted labels and the lexicon
   system, NOT inter-annotator agreement.
2. Curated items are hand-style single sentences; templated items are
   generated from deterministic frames and marked ``source=family``. Nothing
   pretends to be organic scraped news.
3. The set is deduplicated; exact duplicate texts are dropped.

Run:  python scripts/build_gold_set.py [--write-baseline]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naijafinsent.annotation.splits import SplitItem, build_splits, verify_no_leakage  # noqa: E402
from naijafinsent.constants import SENTIMENT_LABELS  # noqa: E402

from goldset.real_items import REAL_ITEMS  # noqa: E402
from goldset.templates import build_templated  # noqa: E402

GOLD_DIR = ROOT / "data" / "annotation" / "gold"
SEED = 42
SPLIT_SEED = 7


def assemble() -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    curated = 0
    for raw in REAL_ITEMS:
        text = " ".join(raw["text"].split())
        if text in seen:
            continue
        seen.add(text)
        curated += 1
        items.append(_mk_item(text, raw, family="curated"))
    for raw in build_templated():
        text = " ".join(raw["text"].split())
        if text in seen:
            continue
        seen.add(text)
        items.append(_mk_item(text, raw, family=next(m for m in raw["markers"] if m.startswith("templated"))))
    # Deterministic order: sort by (family, text) then assign ids.
    items.sort(key=lambda i: (i["source"], i["text"]))
    for n, it in enumerate(items, start=1):
        it["item_id"] = f"g7-{n:05d}"
    return items


def _mk_item(text: str, raw: dict, family: str) -> dict:
    label = raw["label"]
    if label not in SENTIMENT_LABELS:
        raise ValueError(f"bad label {label!r} in {text[:40]!r}")
    return {
        "item_id": "",  # filled after sorting
        "text": text,
        "sentiment": {
            "label": label,
            "annotator": "model-assisted-glm",
            "model_prelabel": True,
        },
        "markers": sorted(set(raw["markers"])),
        "topic": raw["topic"],
        "entities": raw.get("entities") or [],
        "events": raw.get("events") or [],
        "entity_sentiments": raw.get("entity_sentiments") or {},
        "source": family,
        "is_synthetic": family != "curated",
    }


def _spread_dates(items: list[dict]) -> None:
    """Deterministic synthetic publish dates so test_time has something to hold out."""
    today = date(2026, 10, 26)
    for n, it in enumerate(items):
        it["published_at"] = (today - timedelta(days=365 - (n * 365 // max(len(items), 1)))).isoformat()


def assign_splits(items: list[dict]) -> dict:
    split_items = [
        SplitItem(
            item_id=it["item_id"],
            publisher=it["source"],
            published_at=None,  # builder sets time split below
            sentiment_label=it["sentiment"]["label"],
            event_types=tuple(e["event_type"] for e in it["events"]),
        )
        for it in items
    ]
    for it, si in zip(items, split_items, strict=True):
        si.published_at = datetime.fromisoformat(it["published_at"])
    bundle = build_splits(split_items, seed=SPLIT_SEED)
    problems = verify_no_leakage(bundle)
    if problems:
        raise SystemExit(f"split leakage: {problems[:5]}")

    # Flat split = the random view; test segment is named test_random.
    flat: dict[str, str] = {}
    for segment, ids in bundle.views["random"].items():
        key = "test_random" if segment == "test" else segment
        for item_id in ids:
            flat[item_id] = key
    memberships: dict[str, str] = {}
    for view, table in bundle.views.items():
        for segment, ids in table.items():
            for item_id in ids:
                memberships.setdefault(item_id, ""),
                if "test" in segment:
                    memberships[item_id] = f"{memberships[item_id]}+{view}.{segment}" if memberships[item_id] else f"{view}.{segment}"
    for it in items:
        it["split"] = flat.get(it["item_id"], "train")
        it["split_views"] = sorted(filter(None, [memberships.get(it["item_id"], "")]))
    return bundle.sizes()


def write_outputs(items: list[dict], view_sizes: dict) -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLD_DIR / "gold_set.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            row = {k: v for k, v in it.items()}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    labels = Counter(it["sentiment"]["label"] for it in items)
    markers = Counter(m for it in items for m in it["markers"])
    families = Counter(it["source"] for it in items)
    flat_splits = Counter(it["split"] for it in items)
    topics = Counter(it["topic"] for it in items)
    manifest = {
        "n_items": len(items),
        "n_curated_hand_style": sum(1 for it in items if not it["is_synthetic"]),
        "n_templated_synthetic": sum(1 for it in items if it["is_synthetic"]),
        "annotator": "model-assisted-glm (LLM-assisted pass, NO human confirmation yet)",
        "inter_annotator_kappa": None,
        "inter_annotator_kappa_note": (
            "Pending dual human annotation. The gate reports kappa between the "
            "assisted labels and the lexicon system, not between annotators."
        ),
        "labels": dict(labels),
        "markers": dict(markers),
        "topics": dict(topics),
        "families": dict(families),
        "split_sizes_flat": dict(flat_splits),
        "split_view_sizes": view_sizes,
        "split_seed": SPLIT_SEED,
        "entity_targets": sum(1 for it in items if it["entity_sentiments"]),
        "entity_target_examples": sum(len(it["entity_sentiments"]) for it in items),
    }
    (GOLD_DIR / "gold_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def main() -> int:
    items = assemble()
    _spread_dates(items)
    view_sizes = assign_splits(items)
    write_outputs(items, view_sizes)
    print(f"wrote {len(items)} items to {GOLD_DIR / 'gold_set.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
