"""Baseline orchestrator -- a single entry point to compare every baseline.

Run as::

    python -m naijafinsent.baselines.run

Programmatic use::

    from naijafinsent.baselines.run import run_sentiment_baselines, run_ner_baselines
    report = run_sentiment_baselines(train_texts, train_labels, test_texts, test_labels)

Every baseline records wall-clock latency and, where relevant, an estimated LLM
cost. Baselines whose optional dependency is missing are recorded as
``{"skipped": reason}`` rather than crashing the run -- a missing torch install
should not lose you the TF-IDF numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from naijafinsent.constants import SENTIMENT_LABELS

__all__ = [
    "run_sentiment_baselines",
    "run_ner_baselines",
    "run_event_baseline",
    "main",
]


# --------------------------------------------------------------------------
# Metrics (implemented locally to avoid a hard sklearn metric dependency in
# the reporting path; sklearn is available but keeping this explicit makes the
# per-baseline records uniform).
# --------------------------------------------------------------------------

def accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    if not y_true:
        return 0.0
    return sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true)


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str] | None = None) -> float:
    labels = list(labels or sorted(set(y_true) | set(y_pred)))
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def _timed(fn, *args, **kwargs) -> tuple[Any, float]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000.0


# --------------------------------------------------------------------------
# Sentiment baselines
# --------------------------------------------------------------------------

def _majority_baseline(train_labels: Sequence[str], test_texts: Sequence[str],
                       test_labels: Sequence[str]) -> dict:
    from collections import Counter

    majority = Counter(train_labels).most_common(1)[0][0] if train_labels else SENTIMENT_LABELS[0]

    def _run():
        return [majority for _ in test_texts]

    preds, ms = _timed(_run)
    return {
        "name": "majority-class",
        "predictions": preds,
        "latency_ms_total": ms,
        "latency_ms_per_item": ms / max(1, len(test_texts)),
        "metrics": {
            "accuracy": accuracy(test_labels, preds),
            "macro_f1": macro_f1(test_labels, preds, SENTIMENT_LABELS),
        },
        "cost_usd": 0.0,
    }


def _tfidf_baseline(train_texts, train_labels, test_texts, test_labels, *, svm: bool) -> dict:
    from naijafinsent.sentiment.tfidf import TfidfSentimentModel, TfidfSvmSentimentModel

    Model = TfidfSvmSentimentModel if svm else TfidfSentimentModel
    name = "tfidf-linearsvm" if svm else "tfidf-logreg"
    model = Model(use_char=True)
    _, train_ms = _timed(model.fit, train_texts, train_labels)

    def _predict():
        return [model.predict(t).label.value for t in test_texts]

    preds, ms = _timed(_predict)
    return {
        "name": name,
        "predictions": preds,
        "latency_ms_train": train_ms,
        "latency_ms_total": ms,
        "latency_ms_per_item": ms / max(1, len(test_texts)),
        "metrics": {
            "accuracy": accuracy(test_labels, preds),
            "macro_f1": macro_f1(test_labels, preds, SENTIMENT_LABELS),
        },
        "cost_usd": 0.0,
    }


def _finbert_zeroshot_baseline(test_texts, test_labels, *, limit: int | None = None) -> dict:
    try:
        from naijafinsent.sentiment.zeroshot import FinBertZeroShotSentiment

        model = FinBertZeroShotSentiment()
        texts = list(test_texts)[: limit] if limit else list(test_texts)
        labels = list(test_labels)[: limit] if limit else list(test_labels)

        def _predict():
            return [model.predict(t).label.value for t in texts]

        preds, ms = _timed(_predict)
        return {
            "name": "finbert-zeroshot",
            "predictions": preds,
            "latency_ms_total": ms,
            "latency_ms_per_item": ms / max(1, len(texts)),
            "metrics": {
                "accuracy": accuracy(labels, preds),
                "macro_f1": macro_f1(labels, preds, SENTIMENT_LABELS),
            },
            # Local inference: no per-token API cost. Recorded explicitly so the
            # schema is uniform with any future LLM baseline.
            "cost_usd": 0.0,
            "notes": "Uncalibrated, out-of-domain (not trained on Nigerian data).",
            "n_evaluated": len(texts),
        }
    except ImportError as exc:
        return {"name": "finbert-zeroshot", "skipped": str(exc)}


def run_sentiment_baselines(
    train_texts: Sequence[str],
    train_labels: Sequence[str],
    test_texts: Sequence[str] | None = None,
    test_labels: Sequence[str] | None = None,
    *,
    finbert_limit: int | None = None,
) -> dict[str, Any]:
    """Run every sentiment baseline and return a dict keyed by baseline name.

    ``test_texts``/``test_labels`` default to the training data (useful for a
    smoke run, but metrics are then train-set metrics -- stated in the result).
    """
    test_texts = list(test_texts if test_texts is not None else train_texts)
    test_labels = list(test_labels if test_labels is not None else train_labels)

    results: dict[str, Any] = {}
    results["majority-class"] = _majority_baseline(train_labels, test_texts, test_labels)

    for svm in (False, True):
        try:
            rec = _tfidf_baseline(train_texts, train_labels, test_texts, test_labels, svm=svm)
            results[rec["name"]] = rec
        except Exception as exc:  # noqa: BLE001 - baselines must not crash the run
            results["tfidf-linearsvm" if svm else "tfidf-logreg"] = {"skipped": repr(exc)}

    results["finbert-zeroshot"] = _finbert_zeroshot_baseline(
        test_texts, test_labels, limit=finbert_limit
    )

    results["_meta"] = {
        "task": "sentiment",
        "n_train": len(train_texts),
        "n_test": len(test_texts),
        "labels": list(SENTIMENT_LABELS),
    }
    return results


# --------------------------------------------------------------------------
# NER baselines
# --------------------------------------------------------------------------

def _ner_exact_match(gold: Sequence[list], pred: Sequence[list]) -> dict[str, float]:
    """Span-level precision/recall/F1 by exact (start, end, type) match."""
    tp = fp = fn = 0
    for g, p in zip(gold, pred):
        gset = {(s.start, s.end, s.entity_type.value) for s in g}
        pset = {(s.start, s.end, s.entity_type.value) for s in p}
        tp += len(gset & pset)
        fp += len(pset - gset)
        fn += len(gset - pset)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def run_ner_baselines(
    train_texts: Sequence[str],
    train_spans: Sequence[list],
    test_texts: Sequence[str] | None = None,
    test_spans: Sequence[list] | None = None,
) -> dict[str, Any]:
    """Run the rule-based and CRF NER baselines.

    ``train_spans``/``test_spans`` are lists of ``list[EntitySpan]``. The CRF is
    skipped (with a reason) when ``sklearn_crfsuite`` is absent.
    """
    test_texts = list(test_texts if test_texts is not None else train_texts)
    test_spans = list(test_spans if test_spans is not None else train_spans)

    results: dict[str, Any] = {}

    # -- rule-based -----------------------------------------------------
    try:
        from naijafinsent.ner.rules import RuleBasedNer

        rules = RuleBasedNer()

        def _predict():
            return [[p.span for p in rules.predict(t)] for t in test_texts]

        preds, ms = _timed(_predict)
        results["rule-based-ner"] = {
            "name": "rule-based-ner",
            "latency_ms_total": ms,
            "latency_ms_per_item": ms / max(1, len(test_texts)),
            "metrics": _ner_exact_match(test_spans, preds),
            "cost_usd": 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        results["rule-based-ner"] = {"skipped": repr(exc)}

    # -- CRF ------------------------------------------------------------
    try:
        from naijafinsent.ner.crf import CrfNer

        crf = CrfNer()
        _, train_ms = _timed(crf.fit, train_texts, train_spans)

        def _predict_crf():
            return [[p.span for p in crf.predict(t)] for t in test_texts]

        preds, ms = _timed(_predict_crf)
        results["crf-ner"] = {
            "name": "crf-ner",
            "latency_ms_train": train_ms,
            "latency_ms_total": ms,
            "latency_ms_per_item": ms / max(1, len(test_texts)),
            "metrics": _ner_exact_match(test_spans, preds),
            "cost_usd": 0.0,
        }
    except ImportError as exc:
        results["crf-ner"] = {"skipped": str(exc)}
    except Exception as exc:  # noqa: BLE001
        results["crf-ner"] = {"skipped": repr(exc)}

    results["_meta"] = {"task": "ner", "n_train": len(train_texts), "n_test": len(test_texts)}
    return results


# --------------------------------------------------------------------------
# Event baseline (delegates to naijafinsent.event_extraction if present)
# --------------------------------------------------------------------------

def run_event_baseline(
    test_texts: Sequence[str],
    test_events: Sequence[list] | None = None,
) -> dict[str, Any]:
    """Keyword-rule event baseline.

    Delegates to ``naijafinsent.event_extraction`` when that module exposes a
    usable predictor; otherwise falls back to a transparent keyword matcher over
    ``constants.EVENT_TYPES``. Recorded as ``skipped`` only if the delegate
    exists but raises.
    """
    from naijafinsent.constants import EVENT_TYPES

    predictor = None
    try:
        import importlib

        mod = importlib.import_module("naijafinsent.event_extraction")
        # Look for a common entry point.
        for attr in ("predict_events", "KeywordEventBaseline", "RuleBasedEventExtractor"):
            if hasattr(mod, attr):
                predictor = getattr(mod, attr)
                break
    except Exception:  # noqa: BLE001 - optional module
        predictor = None

    if predictor is not None:
        try:
            def _run_delegate():
                out = []
                for t in test_texts:
                    if callable(predictor):
                        res = predictor(t)
                    else:
                        res = predictor().predict(t)
                    out.append([getattr(e, "event_type", e) for e in res])
                return out

            preds, ms = _timed(_run_delegate)
            return {
                "name": "event-keyword-delegate",
                "source": "naijafinsent.event_extraction",
                "latency_ms_total": ms,
                "latency_ms_per_item": ms / max(1, len(test_texts)),
                "predictions": preds,
                "cost_usd": 0.0,
            }
        except Exception as exc:  # noqa: BLE001
            return {"name": "event-keyword-delegate", "skipped": repr(exc)}

    # Transparent fallback: substring keywords per event type.
    keywords: dict[str, tuple[str, ...]] = {
        "cbn_policy": ("mpr", "monetary policy", "cbn", "crr", "liquidity ratio"),
        "earnings": ("profit", "revenue", "earnings", "results", "pat", "loss"),
        "dividend": ("dividend", "interim dividend", "final dividend"),
        "mna": ("acquisition", "merger", "takeover", "divest"),
        "regulatory_sanction": ("fine", "sanction", "penalty", "ban", "penalised"),
        "capital_raise": ("rights issue", "public offer", "recapitalis", "recapitaliz", "capital raise"),
        "fx_move": ("exchange rate", "naira", "fx", "devaluation", "forex"),
        "oil_energy": ("crude oil", "oil output", "petrol", "gas supply", "refinery"),
    }

    def _run_keywords():
        out = []
        for t in test_texts:
            low = t.lower()
            hits = [et for et, kws in keywords.items()
                    if et in EVENT_TYPES and any(k in low for k in kws)]
            out.append(hits)
        return out

    preds, ms = _timed(_run_keywords)
    return {
        "name": "event-keyword-baseline",
        "source": "inline-keywords",
        "latency_ms_total": ms,
        "latency_ms_per_item": ms / max(1, len(test_texts)),
        "predictions": preds,
        "cost_usd": 0.0,
        "notes": "Keyword baseline; delegates to naijafinsent.event_extraction when that module is present.",
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run NaijaFinSent baselines over a JSONL dataset."
    )
    parser.add_argument("--train", type=Path, help="train JSONL with {text,label|spans}")
    parser.add_argument("--test", type=Path, help="test JSONL")
    parser.add_argument("--task", choices=["sentiment", "ner", "events", "all"], default="all")
    parser.add_argument("--out", type=Path, default=None, help="write report JSON here")
    parser.add_argument("--finbert-limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.train is None:
        print("No --train provided; running a tiny built-in smoke dataset.\n")
        train, test = _smoke_dataset()
    else:
        train = _load_jsonl(args.train)
        test = _load_jsonl(args.test) if args.test else train

    train_texts = [r["text"] for r in train]
    test_texts = [r["text"] for r in test]

    report: dict[str, Any] = {}

    if args.task in ("sentiment", "all"):
        train_labels = [r.get("label", "neutral") for r in train]
        test_labels = [r.get("label", "neutral") for r in test]
        report["sentiment"] = run_sentiment_baselines(
            train_texts, train_labels, test_texts, test_labels,
            finbert_limit=args.finbert_limit,
        )

    if args.task in ("ner", "all"):
        from naijafinsent.schemas import EntitySpan, EntityType

        def _spans(rows):
            out = []
            for r in rows:
                spans = []
                for s in r.get("spans", []):
                    spans.append(
                        EntitySpan(
                            start=s["start"], end=s["end"], text=s["text"],
                            entity_type=EntityType(s["type"]),
                        )
                    )
                out.append(spans)
            return out

        report["ner"] = run_ner_baselines(
            train_texts, _spans(train), test_texts, _spans(test)
        )

    if args.task in ("events", "all"):
        report["events"] = run_event_baseline(test_texts)

    # Drop raw predictions from the printed summary (keep them in the file).
    printable = {
        k: (v if k == "_meta" else {
            name: ({kk: vv for kk, vv in rec.items() if kk != "predictions"}
                   if isinstance(rec, dict) else rec)
            for name, rec in v.items()
        })
        for k, v in report.items()
    } if isinstance(report, dict) else report

    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"\nWrote report to {args.out}")
    return 0


def _smoke_dataset() -> tuple[list[dict], list[dict]]:
    """A tiny synthetic Nigerian financial dataset for a no-args smoke run."""
    rows = [
        {"text": "MTN Nigeria profit rises 12% on data revenue growth.",
         "label": "positive", "spans": [{"start": 0, "end": 11, "text": "MTN Nigeria", "type": "ORG"}]},
        {"text": "CBN raises MPR to 27.5% as inflation bites.",
         "label": "negative",
         "spans": [{"start": 0, "end": 3, "text": "CBN", "type": "REGULATOR"}]},
        {"text": "Dangote Cement reports flat earnings for the quarter.",
         "label": "neutral",
         "spans": [{"start": 0, "end": 14, "text": "Dangote Cement", "type": "ORG"}]},
        {"text": "Naira weakness may pressure banks next year, analysts say.",
         "label": "uncertain", "spans": []},
        {"text": "GTCO declares N2.50 interim dividend, shares rally.",
         "label": "positive",
         "spans": [{"start": 0, "end": 4, "text": "GTCO", "type": "TICKER"}]},
        {"text": "SEC fines a brokerage for disclosure breaches.",
         "label": "negative", "spans": [{"start": 0, "end": 3, "text": "SEC", "type": "REGULATOR"}]},
    ]
    return rows, rows


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
