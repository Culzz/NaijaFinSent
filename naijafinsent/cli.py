"""Command-line entry point for NaijaFinSent.

Usage:
    python -m naijafinsent.cli demo                 # run the offline stub pipeline
    python -m naijafinsent.cli ingest --source X    # fetch a source (respects ToS)
    python -m naijafinsent.cli dedupe               # dedup report over a corpus
    python -m naijafinsent.cli splits build         # build locked splits
    python -m naijafinsent.cli eval run             # run the evaluation harness
    python -m naijafinsent.cli version

Every subcommand degrades gracefully: if an optional module is missing it prints
an actionable message instead of a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from naijafinsent import __version__
from naijafinsent.config import get_settings
from naijafinsent.utils import truncate

DEMO_TEXT = (
    "The Central Bank of Nigeria raised the monetary policy rate by 200 basis points "
    "to 24.75 percent, a move analysts said would tighten naira liquidity. "
    "Dangote Cement (DANGCEM) posted a 12 percent rise in profit, while MTN Nigeria "
    "warned that FX losses could weigh on full-year earnings. "
    "The naira closed at N1,480 to the dollar in the parallel market."
)


def _simple_sentiment(text: str):
    """Deterministic offline fallback so `demo` works with zero models."""
    from naijafinsent.schemas import (
        EvidenceSpan,
        ModelRef,
        SentimentLabel,
        SentimentPrediction,
    )

    lowered = text.lower()
    pos = ("rise", "profit", "gains", "growth", "record", "beat", "surge", "rally")
    neg = ("loss", "fall", "decline", "fine", "sanction", "default", "warn", "drop")
    uncertain = ("could", "may", "might", "if", "uncertain", "warned")
    p = sum(w in lowered for w in pos)
    n = sum(w in lowered for w in neg)
    u = sum(w in lowered for w in uncertain)
    if u and abs(p - n) <= 1:
        label = SentimentLabel.UNCERTAIN
    elif p > n:
        label = SentimentLabel.POSITIVE
    elif n > p:
        label = SentimentLabel.NEGATIVE
    else:
        label = SentimentLabel.NEUTRAL
    first = text.split(". ")[0]
    return SentimentPrediction(
        label=label,
        confidence=0.5,
        probabilities={label.value: 0.5, "neutral": 0.25, "uncertain": 0.25},
        evidence=[EvidenceSpan(text=first, start=0, end=len(first))],
        model=ModelRef(name="offline-keyword", version="0.1.0", task="sentiment",
                       calibrated=False),
    )


def _simple_entities(text: str):
    from naijafinsent.preprocessing.lexicon import Lexicon
    from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType

    lex = Lexicon()
    spans = lex.match(text)
    return [
        EntityPrediction(span=s, entity_id=None, canonical_name=s.text,
                         resolution_method="lexicon", confidence=0.6)
        for s in spans
        if s.entity_type in {e for e in EntityType}
    ], EntityType


def cmd_demo(args: argparse.Namespace) -> int:
    from naijafinsent.inference.pipeline import AnalysisPipeline

    text = args.text or DEMO_TEXT
    pipeline = AnalysisPipeline(sentiment_model=None, ner_model=None, event_model=None)

    # Use the lexicon NER if available (framework-free, always importable).
    try:
        from naijafinsent.preprocessing.lexicon import Lexicon
        from naijafinsent.schemas import EntityPrediction

        class _LexNer:
            name = "lexicon-ner"
            version = "0.1.0"
            task = "ner"
            calibrated = False

            def __init__(self) -> None:
                self._lex = Lexicon()

            def predict(self, t: str) -> list[EntityPrediction]:
                return [
                    EntityPrediction(span=s, canonical_name=s.text,
                                     resolution_method="lexicon", confidence=0.6)
                    for s in self._lex.match(t)
                ]

        pipeline.ner_model = _LexNer()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] lexicon NER unavailable: {exc}", file=sys.stderr)

    class _OfflineSentiment:
        name = "offline-keyword"
        version = "0.1.0"
        task = "sentiment"
        calibrated = False

        def predict(self, t: str):  # noqa: ANN201
            return _simple_sentiment(t)

    pipeline.sentiment_model = _OfflineSentiment()

    try:
        from naijafinsent.event_extraction.keywords import KeywordEventModel

        pipeline.event_model = KeywordEventModel()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] event model unavailable: {exc}", file=sys.stderr)

    result = pipeline.analyze(text)
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print()
    print("NOTE:", get_settings().disclaimer)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        from naijafinsent.data.ingest import Ingestor
    except Exception as exc:  # noqa: BLE001
        print(f"ingestion module unavailable ({exc}). Run: pip install -e '.[dev,api]'")
        return 2
    ing = Ingestor()
    report = ing.ingest_source(
        args.source, limit=args.limit, dry_run=args.dry_run,
        allow_unverified=args.allow_unverified,
    )
    print(json.dumps(report, indent=2, default=str) if isinstance(report, dict)
          else str(report))
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    try:
        from naijafinsent.data.store import CorpusStore
    except Exception as exc:  # noqa: BLE001
        print(f"store unavailable ({exc})")
        return 2
    store = CorpusStore(get_settings().data_dir / "corpus.db")
    articles = list(store.iter_articles())
    try:
        from naijafinsent.data.dedup import dedup_report, find_near_duplicates

        clusters = find_near_duplicates(articles, threshold=args.threshold)
        print(json.dumps(dedup_report(clusters), indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(f"dedup unavailable ({exc}); {len(articles)} articles loaded")
    return 0


def cmd_splits(args: argparse.Namespace) -> int:
    try:
        from naijafinsent.annotation.splits import build_splits, verify_no_leakage
    except Exception as exc:  # noqa: BLE001
        print(f"splits module unavailable ({exc})")
        return 2
    print("splits module present. Provide a records file to build splits:")
    print("  python -m naijafinsent.cli splits build --records data/annotation/records.jsonl")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    try:
        from naijafinsent.evaluation import runner
    except Exception as exc:  # noqa: BLE001
        print(f"evaluation module unavailable ({exc})")
        return 2
    argv = []
    if args.action:
        argv.append(args.action)
    return int(runner.main(argv) or 0)


def cmd_version(args: argparse.Namespace) -> int:
    print(f"naijafinsent {__version__}")
    print("not investment advice:", truncate(get_settings().disclaimer, 80))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="naijafinsent", description="NaijaFinSent CLI")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="run the offline stub pipeline on demo text")
    d.add_argument("--text", default=None)
    d.set_defaults(func=cmd_demo)

    i = sub.add_parser("ingest", help="fetch a registered source")
    i.add_argument("--source", required=True)
    i.add_argument("--limit", type=int, default=20)
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--allow-unverified", action="store_true")
    i.set_defaults(func=cmd_ingest)

    dd = sub.add_parser("dedupe", help="run the dedup report over a stored corpus")
    dd.add_argument("--threshold", type=float, default=0.85)
    dd.set_defaults(func=cmd_dedupe)

    s = sub.add_parser("splits", help="build or verify locked splits")
    s.add_argument("action", choices=["build", "verify"], nargs="?", default="build")
    s.add_argument("--records", default="data/annotation/records.jsonl")
    s.set_defaults(func=cmd_splits)

    e = sub.add_parser("eval", help="run the evaluation harness")
    e.add_argument("action", nargs="?", default="report",
                   choices=["bench", "experiments", "report"])
    e.set_defaults(func=cmd_eval)

    v = sub.add_parser("version", help="print version")
    v.set_defaults(func=cmd_version)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
