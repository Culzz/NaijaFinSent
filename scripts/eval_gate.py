"""Golden-set evaluation regression gate.

Runs a fixed, committed set of Nigerian financial-news sentences through the
deterministic pipeline and compares accuracy against a frozen baseline JSON.
CI fails if quality drops by more than ``--tolerance``.

This is deliberately small and deterministic: it protects the *offline demo
path* (stub pipeline, keyword models) from silent regressions. The locked
NaijaFin-Bench test split remains the research-grade benchmark and is never
tuned on (see docs/REPRODUCE.md).

Exit codes: 0 = within tolerance, 1 = regression, 2 = baseline missing
(first run: use --write-baseline to create it, then commit the file).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naijafinsent.inference.pipeline import StubPipeline  # noqa: E402

# Committed golden set: (text, expected_sentiment_label).
# Labels follow the four sentiment labels in constants.SENTIMENT_LABELS.
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

BASELINE_PATH = ROOT / "research" / "baselines" / "golden_baseline.json"


def macro_f1(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def run(verbose: bool = True) -> dict:
    pipeline = StubPipeline()
    correct = 0
    misses: list[dict] = []
    for text, expected in GOLDEN_SET:
        result = pipeline.analyze(text)
        if isinstance(result, dict):
            pred = (result.get("sentiment") or {}).get("label")
        else:
            pred = getattr(getattr(result, "sentiment", None), "label", None)
        ok = pred == expected
        correct += int(ok)
        if not ok and verbose:
            misses.append({"text": text[:60], "expected": expected, "got": pred})
    accuracy = round(correct / len(GOLDEN_SET), 4)
    if verbose:
        for miss in misses:
            print(f"  MISS: {miss}")
        print(f"golden accuracy: {correct}/{len(GOLDEN_SET)} = {accuracy}")
    return {"accuracy": accuracy, "n": len(GOLDEN_SET), "correct": correct}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--write-baseline", action="store_true",
                        help="overwrite the frozen baseline with current results")
    args = parser.parse_args(argv)

    current = run()
    accuracy = current["accuracy"]

    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
        print(f"baseline written -> {BASELINE_PATH.relative_to(ROOT)}")

    if not BASELINE_PATH.exists():
        print(f"baseline missing: {BASELINE_PATH.relative_to(ROOT)}", file=sys.stderr)
        print("run scripts/eval_gate.py --write-baseline, then commit the file", file=sys.stderr)
        return 2

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    expected = baseline.get("accuracy", 0.0)
    if accuracy >= expected - args.tolerance:
        print(f"OK: accuracy {accuracy} >= {expected} - {args.tolerance}")
        return 0
    print(f"REGRESSION: accuracy {accuracy} < {expected} - {args.tolerance}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
