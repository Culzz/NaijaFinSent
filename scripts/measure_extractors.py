"""Measure the rule-based extractors against the committed gold set.

Produces, per type, the numbers the credibility roadmap asks for:

* **Events**     — precision / recall per event type, recall treated as the
  priority metric (an event the pipeline missed can never be tracked),
  with item-level percentile bootstrap CIs;
* **NER spans**  — precision / recall per entity type via surface-form match
  (the gold set records entity text, not offsets — stated openly),
  with bootstrap CIs on both.

Counts of gold items supporting each cell are printed alongside every rate:
a per-type recall of 1.00 on 7 gold items is not the same fact as 0.60 on 400.
Nothing here feeds back into the lexicon — this script only measures.

Output: ``research/reports/extractor_metrics.json`` plus a markdown table on
stdout. Run: ``python scripts/measure_extractors.py``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naijafinsent.schemas import EntityType, EventType  # noqa: E402
from naijafinsent.inference.pipeline import StubPipeline  # noqa: E402

GOLD_PATH = ROOT / "data" / "annotation" / "gold" / "gold_set.jsonl"
REPORT_PATH = ROOT / "research" / "reports" / "extractor_metrics.json"

BOOTSTRAP_ROUNDS = 1000
SEED = 1729


def _norm_entity(text: str) -> str:
    """Surface-form normalisation for entity matching (no offsets in gold)."""
    t = " ".join(str(text).split()).casefold()
    if t.startswith("the "):
        t = t[4:]
    while t and t[-1] in ".,;:!":
        t = t[:-1]
    return t


def _entity_match(gold: str, predicted: str) -> bool:
    g, p = _norm_entity(gold), _norm_entity(predicted)
    if not g or not p:
        return False
    if g == p:
        return True
    # The gold text may sit inside a longer predicted span ("Zenith Bank" in
    # "Zenith Bank's profit"), but a shorter alias ("MTN") must not satisfy a
    # longer gold mention ("MTN Group").
    return f" {g} " in f" {p} "


def _bootstrap_ci(matches: list[int], seed_offset: int) -> list[float]:
    if not matches:
        return [None, None]
    rng = __import__("random").Random(SEED + seed_offset)
    n = len(matches)
    means = []
    for _ in range(BOOTSTRAP_ROUNDS):
        sample = [matches[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return [round(means[int(0.025 * len(means))], 4), round(means[int(0.975 * len(means))], 4)]


def main() -> int:
    items = [json.loads(l) for l in GOLD_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    pipeline = StubPipeline()

    event_gold_support: dict[str, set[int]] = {t.value: set() for t in EventType}
    event_pred_counts: Counter = Counter()
    event_match_flags: dict[str, list[int]] = {}          # per gold event: matched
    event_precision_flags: dict[str, list[int]] = {}      # per predicted: supported

    ner_gold: list[tuple[str, str]] = []                  # (type, text)
    ner_pred: list[tuple[str, str, int]] = []             # (type, text, item_idx)

    for idx, it in enumerate(items):
        gold_events = [e["event_type"] for e in it.get("events", [])]
        for et in gold_events:
            event_gold_support.setdefault(et, set()).add(idx)

        gold_entities = [(e["entity_type"], e["text"]) for e in it.get("entities", [])]
        ner_gold.extend(gold_entities)

        result = pipeline.analyze(it["text"])
        pred_ev_types = [getattr(e.event_type, "value", e.event_type) for e in result.events]
        for et in pred_ev_types:
            event_pred_counts[et] += 1
            event_precision_flags.setdefault(et, []).append(int(idx in event_gold_support.get(et, set())))

        for et in gold_events:
            matched = int(et in pred_ev_types)
            event_match_flags.setdefault(et, []).append(matched)

        for e in result.entities:
            surface = getattr(e.span, "text", "") or ""
            etype = getattr(e.span, "entity_type", None)
            etype = getattr(etype, "value", etype)
            if etype in {"MONEY", "CURRENCY", "EVENT_TRIGGER", "SECTOR"}:
                continue  # not measured against the gold ORG/REGULATOR set
            ner_pred.append((etype, surface, idx))

    report: dict = {"n_items": len(items), "seed": SEED, "bootstrap_rounds": BOOTSTRAP_ROUNDS}

    # -- events -------------------------------------------------------------
    events_md = []
    for et in [t.value for t in EventType]:  # fixed order, gaps visible
        gold_n = len(event_gold_support.get(et, set()))
        pred_n = event_pred_counts.get(et, 0)
        matches = event_match_flags.get(et, [])
        prec_flags = event_precision_flags.get(et, [])
        if gold_n:
            recall = sum(matches) / len(matches)
            rci = _bootstrap_ci(matches, hash(et) % 10000)
        else:
            recall = rci = None
        if prec_flags:
            precision = sum(prec_flags) / len(prec_flags)
            pci = _bootstrap_ci(prec_flags, 5000 + hash(et) % 10000)
        else:
            precision = pci = None
        report.setdefault("events", {})[et] = {
            "n_gold": gold_n,
            "n_predicted": pred_n,
            "recall": None if recall is None else round(recall, 4),
            "precision": None if precision is None else round(precision, 4),
            "recall_ci95": rci,
            "precision_ci95": pci,
        }
        events_md.append(
            f"| {et} | {gold_n} | {pred_n} | "
            + (f"{recall:.2f} [{rci[0]:.2f}–{rci[1]:.2f}]" if recall is not None else "—") + " | "
            + (f"{precision:.2f} [{pci[0]:.2f}–{pci[1]:.2f}]" if precision is not None else "—") + " |"
        )

    # -- NER ------------------------------------------------------------------
    # Per-item matching, exactly what the pipeline sees: recall counts a gold
    # mention only if a predicted span IN THAT ITEM matches it; precision only
    # credits a predicted span whose item carries a matching gold mention.
    # ORG/TICKER are one organisation class — the lexicon stores a ticker
    # entry whose aliases are full company names, and the resolver treats both
    # as pointers to the same canonical entity.
    gold_specs: dict[str, set[str]] = {
        "ORG/TICKER": {"ORG", "TICKER"},
        "REGULATOR": {"REGULATOR"},
    }

    gold_entities_by_item: dict[int, dict[str, list[str]]] = {}
    for idx, it in enumerate(items):
        for e in it.get("entities", []):
            gold_entities_by_item.setdefault(idx, {}).setdefault(
                e["entity_type"], []
            ).append(e["text"])

    def _class_of(pred_type: str) -> str | None:
        for cls, types in gold_specs.items():
            if pred_type.upper() in types:
                return cls
        return None

    ner_report: dict = {}
    ner_md: list[str] = []
    for cls, types in gold_specs.items():
        match_flags: list[int] = []
        for idx, mentions in gold_entities_by_item.items():
            for gtype, gtexts in mentions.items():
                if gtype not in types:
                    continue
                for gtext in gtexts:
                    ok = int(any(
                        _class_of(ptype) == cls and _entity_match(gtext, psurf)
                        for ptype, psurf, pidx in ner_pred
                        if pidx == idx
                    ))
                    match_flags.append(ok)
        if match_flags:
            recall = sum(match_flags) / len(match_flags)
            rci = _bootstrap_ci(match_flags, 9000 + hash(cls) % 10000)
        else:
            recall = rci = None

        preds = [(psurf, pidx) for ptype, psurf, pidx in ner_pred if _class_of(ptype) == cls]
        prec_flags: list[int] = []
        for psurf, pidx in preds:
            mentions = gold_entities_by_item.get(pidx, {})
            golds_here = [g for gt, gs in mentions.items() if gt in types for g in gs]
            ok = int(any(_entity_match(g, psurf) for g in golds_here)) if golds_here else 0
            prec_flags.append(ok)
        if prec_flags:
            precision = sum(prec_flags) / len(prec_flags)
            pci = _bootstrap_ci(prec_flags, 13000 + hash(cls) % 10000)
        else:
            precision = pci = None

        n_gold = sum(
            len([g for gt, gs in m.items() if gt in types for g in gs])
            for m in gold_entities_by_item.values()
        )
        ner_report[cls] = {
            "n_gold": n_gold,
            "n_predicted": len(preds),
            "recall": None if recall is None else round(recall, 4),
            "precision": None if precision is None else round(precision, 4),
            "recall_ci95": rci,
            "precision_ci95": pci,
            "note": (
                "surface-form match within the same item; the gold set records "
                "entity text, not offsets; ORG/TICKER measured as one "
                "organisation class"
            ),
        }
        ner_md.append(
            f"| {cls} | {n_gold} | {len(preds)} | "
            + (f"{recall:.2f} [{rci[0]:.2f}-{rci[1]:.2f}]" if recall is not None else "-") + " | "
            + (f"{precision:.2f} [{pci[0]:.2f}-{pci[1]:.2f}]" if precision is not None else "-") + " |"
        )

    report["ner"] = ner_report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"# Extractor metrics vs gold set (n={len(items)} items, seed {SEED})\n")
    print("## Events (recall prioritised)\n")
    print("| event type | n_gold | n_pred | recall [CI95] | precision [CI95] |")
    print("|---|---|---|---|---|")
    print("\n".join(events_md))
    print("\n## NER spans (surface-form match)\n")
    print("| entity type | n_gold | n_pred | recall [CI95] | precision [CI95] |")
    print("|---|---|---|---|---|")
    print("\n".join(ner_md))
    print(f"\nwrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
