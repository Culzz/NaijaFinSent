"""Evaluation regression gates.

Two committed, deterministic gates protect the offline path:

* **golden**  — the original 12-sentence demo set. Plumbing only: one error
  moves accuracy by 8.3 points, so the tolerance can never catch a single
  regression. Kept because it is the demo-path smoke test.
* **goldset** — the committed gold set (`data/annotation/gold/gold_set.jsonl`,
  1,000+ items). Reports accuracy, macro-F1 over the four labels, Cohen's
  kappa (assisted labels vs system — *not* inter-annotator), a bootstrap CI,
  and per-marker breakdowns (pidgin, naira variants, headline fragments, …).
  Labels are LLM-assisted and await human review — see
  ``data/annotation/gold/README.md``.

Exit codes: 0 = within tolerance, 1 = regression, 2 = baseline missing
(first run: use ``--write-baseline`` then commit the file).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naijafinsent.annotation.agreement import cohens_kappa  # noqa: E402
from naijafinsent.constants import SENTIMENT_LABELS  # noqa: E402
from naijafinsent.evaluation.metrics import bootstrap_ci, macro_f1  # noqa: E402
from naijafinsent.inference.pipeline import StubPipeline  # noqa: E402

GOLD_DIR = ROOT / "data" / "annotation" / "gold"
GOLDSET_PATH = GOLD_DIR / "gold_set.jsonl"
GOLDSET_BASELINE_PATH = ROOT / "research" / "baselines" / "goldset_baseline.json"

# Committed demo set: (text, expected_sentiment_label).
GOLDEN_SET: list[tuple[str, str]] = [
    ("Access Bank posts record profit for the full year, revenue up 34 percent.", "positive"),
    ("Dangote Cement declares final dividend of N25 kobo per share for 2025.", "neutral"),
    ("The naira suffered a sharp depreciation at the parallel market, falling to a record low.", "negative"),
    ("Zenith Bank said its half-year results will be released next week; analysts expect a mixed outcome.", "uncertain"),
    ("NNPC announced a major crude oil production increase following pipeline repairs.", "positive"),
    ("The CBN retained the monetary policy rate at 27.50 percent, leaving developers disappointed.", "negative"),
    ("MTN Nigeria returned to profitability after years of losses.", "positive"),
    ("Investors are still waiting for the outcome of the recapitalisation exercise.", "uncertain"),
    ("Guaranty Trust Bank raised N50 billion through a successful rights issue.", "neutral"),
    ("FBN HoldingsLawmakers accused the regulator of undermining the banking sector reforms.", "negative"),
    ("Lagos electricity tariff: regulators approve a modest increase for Band A customers.", "neutral"),
    ("Seplat Energy's planned acquisition of a rival is expected to boost reserves; details remain unclear.", "uncertain"),
]

GOLDEN_BASELINE_PATH = ROOT / "research" / "baselines" / "golden_baseline.json"


def run_pipeline(pipeline: StubPipeline, text: str) -> str:
    result = pipeline.analyze(text)
    if isinstance(result, dict):
        label = (result.get("sentiment") or {}).get("label")
    else:
        label = getattr(getattr(result, "sentiment", None), "label", None)
    return getattr(label, "value", label)


def _accuracy_ci(y: list[str], p: list[str], n: int = 1000, seed: int = 0) -> dict[str, float]:
    yt = np.asarray(y)
    yp = np.asarray(p)

    def acc(_yt, _yp, idx):
        return float(np.mean(yt[idx] == yp[idx]))

    return bootstrap_ci(acc, y, p, n=n, seed=seed)


def run_golden(tolerance: float, write_baseline: bool, verbose: bool = True) -> int:
    baseline_path = GOLDEN_BASELINE_PATH
    if not baseline_path.exists():
        if write_baseline:
            _write_golden_baseline()
            print(f"wrote baseline {baseline_path} — commit it")
            return 0
        print(f"missing baseline: {baseline_path}")
        return 2
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    pipeline = StubPipeline()
    correct = 0
    misses: list[dict] = []
    for text, expected in GOLDEN_SET:
        pred = run_pipeline(pipeline, text)
        if pred == expected:
            correct += 1
        else:
            misses.append({"text": text[:60], "expected": expected, "got": str(pred)})
    accuracy = correct / len(GOLDEN_SET)
    floor = baseline["accuracy"] - tolerance
    if verbose:
        print(f"[golden gate] n={len(GOLDEN_SET)} accuracy={accuracy:.4f} baseline={baseline['accuracy']:.4f} floor={floor:.4f}")
        for m in misses:
            print(f"  MISS: {m}")
    if accuracy < floor:
        print("FAIL: golden gate below tolerance floor")
        return 1
    print("OK: golden gate within tolerance")
    return 0


def run_goldset(tolerance: float, write_baseline: bool, verbose: bool = True) -> int:
    if not GOLDSET_PATH.exists():
        print(f"missing gold set: {GOLDSET_PATH} (run scripts/build_gold_set.py)")
        return 2
    items = [json.loads(line) for line in GOLDSET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    pipeline = StubPipeline()
    y_true: list[str] = []
    y_pred: list[str] = []
    marker_hits: dict[str, Counter] = {}
    for it in items:
        pred = run_pipeline(pipeline, it["text"])
        gold = it["sentiment"]["label"]
        y_true.append(gold)
        y_pred.append(pred)
        for marker in it.get("markers", []):
            c = marker_hits.setdefault(marker, Counter())
            c["total"] += 1
            c["hits"] += int(pred == gold)

    accuracy = float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))
    f1 = macro_f1(y_true, y_pred, SENTIMENT_LABELS)
    kappa = cohens_kappa(y_true, y_pred)
    ci = _accuracy_ci(y_true, y_pred)
    per_marker = {m: c["hits"] / c["total"] for m, c in sorted(marker_hits.items())}

    report = {
        "n": len(items),
        "accuracy": accuracy,
        "macro_f1": f1,
        "kappa_vs_system": kappa,
        "ci95_accuracy": [ci["low"], ci["high"]],
        "per_marker_accuracy": per_marker,
        "annotator": "model-assisted-glm (no human confirmation yet)",
        "note": "kappa is chance-corrected agreement between assisted labels and the lexicon system, NOT inter-annotator agreement",
    }

    if write_baseline:
        GOLDSET_BASELINE_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote baseline {GOLDSET_BASELINE_PATH} — commit it")
        return 0
    if not GOLDSET_BASELINE_PATH.exists():
        print(f"missing baseline: {GOLDSET_BASELINE_PATH} (run with --write-baseline)")
        return 2

    baseline = json.loads(GOLDSET_BASELINE_PATH.read_text(encoding="utf-8"))
    floor = baseline["accuracy"] - tolerance
    if verbose:
        print(f"[goldset gate] n={len(items)} accuracy={accuracy:.4f} (CI95 {ci['low']:.4f}-{ci['high']:.4f}) macro_f1={f1:.4f} kappa={kappa:.4f}")
        print(f"               baseline={baseline['accuracy']:.4f} floor={floor:.4f} n_baseline={baseline['n']}")
        worst = sorted(per_marker.items(), key=lambda kv: kv[1])[:6]
        print("               weakest markers:", ", ".join(f"{m}={v:.2f}" for m, v in worst))
        big_drift = [m for m in per_marker if m in baseline.get("per_marker_accuracy", {}) and baseline["per_marker_accuracy"][m] - per_marker[m] > tolerance]
        if big_drift:
            print("  colored drift:", ", ".join(sorted(big_drift)))
    if baseline["n"] != len(items):
        print(f"WARN: gold set size changed ({baseline['n']} -> {len(items)}); refresh the baseline commit")
    if accuracy < floor:
        print("FAIL: goldset gate below tolerance floor")
        return 1
    print("OK: goldset gate within tolerance")
    return 0


def _write_golden_baseline() -> None:
    pipeline = StubPipeline()
    correct = sum(1 for text, expected in GOLDEN_SET if run_pipeline(pipeline, text) == expected)
    GOLDEN_BASELINE_PATH.write_text(
        json.dumps({"accuracy": correct / len(GOLDEN_SET), "n": len(GOLDEN_SET)}, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--gate", choices=("golden", "goldset", "all"), default="all")
    args = parser.parse_args(argv)

    codes: list[int] = []
    if args.gate in ("golden", "all"):
        codes.append(run_golden(args.tolerance, args.write_baseline))
    if args.gate in ("goldset", "all"):
        codes.append(run_goldset(args.tolerance, args.write_baseline))
    return max(codes) if codes else 0


if __name__ == "__main__":
    raise SystemExit(main())
