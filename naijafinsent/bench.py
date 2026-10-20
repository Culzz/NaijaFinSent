"""NaijaFin-Bench: the open benchmark packaging layer.

This module turns the locked splits plus evaluation runs into the artefacts we
publish:

* ``bench.jsonl`` / per-task JSONL — labels + article URLs + offsets, **never**
  full article text unless the source is an official release or explicitly
  redistributable.
* ``bench.manifest.json`` — dataset version, hash, task counts, split sizes,
  and the exact command that regenerates it.
* submission format + leaderboard assembly.

The legal policy is enforced here in code: :func:`assert_redistributable`
refuses to emit an item whose source licence does not permit text reuse, and
falls back to emitting the URL + spans only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from naijafinsent.config import get_settings
from naijafinsent.schemas import AnnotationRecord
from naijafinsent.utils import sha256_text, slugify, utcnow

BENCH_VERSION = "0.1.0"

# Sources whose text may be redistributed verbatim.
TEXT_REDISTRIBUTABLE: frozenset[str] = frozenset(
    {
        # Official releases published for public reuse. News sources are NOT
        # in this set: we publish labels + URLs + rebuild scripts for them.
    }
)


class RedistributionError(RuntimeError):
    """Raised when asked to publish text we are not allowed to publish."""


@dataclass
class BenchItem:
    """One benchmark item. Text is optional by design."""

    item_id: str
    article_id: str
    split: str
    url: str | None = None
    text: str | None = None
    tasks: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "article_id": self.article_id,
            "split": self.split,
            "url": self.url,
            "text": self.text,
            "tasks": self.tasks,
            "source_id": self.source_id,
            "metadata": self.metadata,
        }


def assert_redistributable(source_id: str | None, *, official_release: bool) -> bool:
    """Return True if we may publish the item's text."""
    if official_release:
        return True
    return bool(source_id and source_id in TEXT_REDISTRIBUTABLE)


def record_to_bench_item(
    record: AnnotationRecord,
    *,
    url: str | None = None,
    source_id: str | None = None,
    official_release: bool = False,
) -> BenchItem:
    """Convert an annotation record into a publishable benchmark item.

    The article text is included ONLY when redistribution is permitted;
    otherwise ``text`` is None and consumers rebuild from the URL.
    """
    tasks: dict[str, Any] = {}
    if record.sentiment is not None:
        tasks["sentiment"] = {
            "label": record.sentiment.label.value,
            "target_entity": record.sentiment.target_entity,
            "rationale_span": (
                record.sentiment.rationale_span.model_dump()
                if record.sentiment.rationale_span
                else None
            ),
        }
    if record.spans:
        tasks["ner"] = [
            {"start": s.start, "end": s.end, "text": s.text,
             "entity_type": s.entity_type.value}
            for s in record.spans
        ]
    if record.money:
        tasks["money"] = [
            {
                "span": m.span.model_dump(),
                "value": m.value,
                "currency": m.currency,
                "unit": m.unit,
            }
            for m in record.money
        ]
    if record.events:
        tasks["events"] = [
            {
                "event_type": e.event_type.value,
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "evidence_span": e.evidence_span.model_dump() if e.evidence_span else None,
                "entities": [x.model_dump() for x in e.entities],
            }
            for e in record.events
        ]

    include_text = assert_redistributable(source_id, official_release=official_release)
    return BenchItem(
        item_id=record.item_id,
        article_id=record.article_id,
        split=record.split,
        url=url,
        text=record.text if include_text else None,
        tasks=tasks,
        source_id=source_id,
        metadata={"text_redistributed": include_text},
    )


# --------------------------------------------------------------------------
# Task-specific views
# --------------------------------------------------------------------------

def sentiment_view(items: Iterable[BenchItem]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        s = it.tasks.get("sentiment")
        if not s:
            continue
        out.append(
            {
                "item_id": it.item_id,
                "split": it.split,
                "url": it.url,
                "text": it.text,
                "label": s["label"],
            }
        )
    return out


def ner_view(items: Iterable[BenchItem]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        spans = it.tasks.get("ner")
        if not spans:
            continue
        out.append(
            {
                "item_id": it.item_id,
                "split": it.split,
                "url": it.url,
                "text": it.text,
                "entities": spans,
            }
        )
    return out


def event_view(items: Iterable[BenchItem]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        events = it.tasks.get("events")
        if not events:
            continue
        out.append(
            {
                "item_id": it.item_id,
                "split": it.split,
                "url": it.url,
                "text": it.text,
                "events": events,
            }
        )
    return out


# --------------------------------------------------------------------------
# Writing the benchmark
# --------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


def build_manifest(items: list[BenchItem], out_dir: Path) -> dict[str, Any]:
    by_split: dict[str, int] = {}
    for it in items:
        by_split[it.split] = by_split.get(it.split, 0) + 1

    task_counts = {"sentiment": 0, "ner": 0, "events": 0, "money": 0}
    for it in items:
        for t in task_counts:
            if it.tasks.get(t):
                task_counts[t] += 1

    digest = sha256_text(
        "\n".join(sorted(f"{it.item_id}:{it.split}" for it in items))
    )
    return {
        "bench_version": BENCH_VERSION,
        "generated_at": utcnow().isoformat(),
        "n_items": len(items),
        "splits": by_split,
        "task_counts": task_counts,
        "dataset_hash": digest,
        "text_redistributed_items": sum(
            1 for it in items if it.metadata.get("text_redistributed")
        ),
        "regenerate_command": (
            "python -m naijafinsent.bench build "
            "--records data/annotation/records.jsonl "
            f"--out {out_dir.as_posix()}"
        ),
        "license_note": (
            "Labels, URLs, and offsets are released for research use. Full article "
            "text is included only for sources whose terms permit redistribution."
        ),
    }


def build_bench(
    records: Iterable[AnnotationRecord],
    out_dir: Path | str | None = None,
    *,
    urls: dict[str, str] | None = None,
    sources: dict[str, str] | None = None,
    official: set[str] | None = None,
) -> dict[str, Any]:
    """Build the full NaijaFin-Bench artefact set on disk."""
    settings = get_settings()
    out = Path(out_dir) if out_dir else settings.data_dir / "bench"
    out.mkdir(parents=True, exist_ok=True)
    urls = urls or {}
    sources = sources or {}
    official = official or set()

    items: list[BenchItem] = []
    for rec in records:
        items.append(
            record_to_bench_item(
                rec,
                url=urls.get(rec.article_id),
                source_id=sources.get(rec.article_id),
                official_release=rec.article_id in official,
            )
        )

    counts = {
        "bench": _write_jsonl(out / "bench.jsonl",
                              (it.to_jsonable() for it in items)),
        "sentiment": _write_jsonl(out / "sentiment.jsonl", sentiment_view(items)),
        "ner": _write_jsonl(out / "ner.jsonl", ner_view(items)),
        "events": _write_jsonl(out / "events.jsonl", event_view(items)),
    }

    manifest = build_manifest(items, out)
    manifest["file_counts"] = counts
    (out / "bench.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (out / "SUBMISSION_FORMAT.md").write_text(SUBMISSION_FORMAT, encoding="utf-8")
    return manifest


SUBMISSION_FORMAT = """# NaijaFin-Bench submission format

Submit one JSONL file per task. Each line is an object keyed by `item_id`.

## Sentiment (`sentiment.jsonl`)
```json
{"item_id": "nfs-000123", "label": "negative", "confidence": 0.81}
```
`label` must be one of: positive, negative, neutral, uncertain.

## NER (`ner.jsonl`)
```json
{"item_id": "nfs-000123", "entities": [{"start": 4, "end": 7, "text": "CBN", "entity_type": "REGULATOR"}]}
```
`entity_type` must be one of: ORG, PER, REGULATOR, MONEY, TICKER, CURRENCY, SECTOR, EVENT_TRIGGER.
Offsets are character offsets into the benchmark text (inclusive start, exclusive end).

## Events (`events.jsonl`)
```json
{"item_id": "nfs-000123", "events": [{"event_type": "cbn_policy", "event_date": "2026-02-19", "evidence_start": 0, "evidence_end": 62}]}
```
`event_type` must be one of: cbn_policy, earnings, dividend, mna, regulatory_sanction,
capital_raise, fx_move, oil_energy.

## Rules
* One prediction per `item_id`; extra or missing ids are scored as errors.
* Never train on items whose `split` is `test*`.
* Report seeds and variance. A single-seed number without variance is not accepted
  onto the leaderboard.
* Submissions must include a model card and a reproducibility statement.
* This benchmark measures language in news coverage. It is **not investment advice**.
"""


def leaderboard_row(
    *,
    model: str,
    task: str,
    metrics: dict[str, float],
    submitter: str | None = None,
    url: str | None = None,
    seeds: int | None = None,
) -> dict[str, Any]:
    """A normalised leaderboard row; callers pick the primary metric per task."""
    primary = {
        "sentiment": "macro_f1",
        "ner": "entity_f1",
        "events": "macro_f1",
        "entity_sentiment": "macro_f1",
    }.get(task, "macro_f1")
    return {
        "model": model,
        "task": task,
        "primary_metric": primary,
        "primary_value": metrics.get(primary),
        "metrics": metrics,
        "seeds": seeds,
        "submitter": submitter,
        "url": url,
        "slug": slugify(f"{model}-{task}"),
        "added_at": utcnow().isoformat(),
    }


def render_leaderboard(rows: list[dict[str, Any]]) -> str:
    """Markdown leaderboard sorted by primary metric descending."""
    lines = [
        "# NaijaFin-Bench leaderboard",
        "",
        "> Coverage-language measurements, not investment advice.",
        "",
    ]
    tasks = sorted({r["task"] for r in rows})
    for task in tasks:
        lines.append(f"## {task}")
        lines.append("")
        lines.append("| Rank | Model | Primary | Seeds | Submitter |")
        lines.append("|---:|---|---|---:|---|")
        subset = [r for r in rows if r["task"] == task]
        subset.sort(key=lambda r: (r.get("primary_value") is None,
                                   -(r.get("primary_value") or 0.0)))
        for i, r in enumerate(subset, start=1):
            val = r.get("primary_value")
            shown = f"{val:.4f}" if isinstance(val, (int, float)) else "n/a"
            lines.append(
                f"| {i} | {r['model']} | {r['primary_metric']} = {shown} | "
                f"{r.get('seeds') or '—'} | {r.get('submitter') or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="naijafinsent.bench")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build benchmark artefacts from records")
    b.add_argument("--records", default="data/annotation/records.jsonl")
    b.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    records: list[AnnotationRecord] = []
    path = Path(args.records)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(AnnotationRecord.model_validate_json(line))
    else:
        print(f"[bench] no records at {path}; writing an empty, valid manifest")

    manifest = build_bench(records, args.out)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
