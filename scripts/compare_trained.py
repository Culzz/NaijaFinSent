"""Trained-model comparison: TF-IDF vs lexicon on the committed gold set.

Trains the TF-IDF family behind the project's scikit-learn dependency
(``TfidfSentimentModel``, ``TfidfSvmSentimentModel``) on the gold **train**
split only, then evaluates it and the deterministic lexicon pipeline on the
frozen-out surfaces (``test_random`` and the held-out views), with the same
metrics as the gate: accuracy, macro-F1, kappa vs the assisted labels, and a
bootstrap CI.

Fairness rules (stated, not implied):

* the trained model sees **only** the ``train`` items — never dev, never any
  test surface;
* model selection is NOT done here: one fixed configuration per family, so
  the comparison number is not a tuned best-case;
* kappa is again assisted-labels-vs-system agreement, not inter-annotator.

Output: ``research/reports/trained_comparison.json`` + markdown on stdout.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naijafinsent.annotation.agreement import cohens_kappa  # noqa: E402
from naijafinsent.constants import SENTIMENT_LABELS  # noqa: E402
from naijafinsent.evaluation.metrics import bootstrap_ci, macro_f1  # noqa: E402
from naijafinsent.inference.pipeline import StubPipeline  # noqa: E402
from naijafinsent.sentiment.tfidf import TfidfSentimentModel, TfidfSvmSentimentModel  # noqa: E402

GOLD_PATH = ROOT / "data" / "annotation" / "gold" / "gold_set.jsonl"
REPORT_PATH = ROOT / "research" / "reports" / "trained_comparison.json"
SEED = 1729


def _load_items() -> list[dict]:
    return [json.loads(l) for l in GOLD_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def _evaluate(name: str, predict: Callable[[str], str], y_true: list[str], seeds: list[int]) -> dict:
    y_pred = [predict(t) for t in (ITEM_TEXTS[i] for i in EVAL_ITEMS)]
    yt = [GOLD_LABELS[i] for i in EVAL_ITEMS]
    acc = float(np.mean(np.asarray(yt) == np.asarray(y_pred)))
    yt_arr, yp_arr = np.asarray(yt), np.asarray(y_pred)

    def acc_fn(_yt, _yp, idx):
        return float(np.mean(yt_arr[idx] == yp_arr[idx]))

    ci = bootstrap_ci(acc_fn, yt, y_pred, n=1000, seed=SEED)
    return {
        "model": name,
        "n": len(yt),
        "accuracy": round(acc, 4),
        "accuracy_ci95": [round(ci["low"], 4), round(ci["high"], 4)],
        "macro_f1": round(macro_f1(yt, y_pred, SENTIMENT_LABELS), 4),
        "kappa_vs_assisted_labels": round(cohens_kappa(yt, y_pred), 4),
    }


def main() -> int:
    global ITEM_TEXTS, GOLD_LABELS, EVAL_ITEMS
    items = _load_items()
    ITEM_TEXTS = [it["text"] for it in items]
    GOLD_LABELS = [it["sentiment"]["label"] for it in items]

    train_idx = [i for i, it in enumerate(items) if it["split"] == "train"]
    EVAL_ITEMS = [i for i, it in enumerate(items) if it["split"] in {"dev", "test_random"}]
    CURATED_EVAL_ITEMS = [i for i in EVAL_ITEMS if not items[i]["is_synthetic"]]

    if len(train_idx) < 100 or len(EVAL_ITEMS) < 100:
        raise SystemExit("gold split too small to compare; regenerate the gold set")

    print(f"train={len(train_idx)} items, eval={len(EVAL_ITEMS)} items (dev+test_random)\n")

    lexicon = StubPipeline()

    def lexicon_predict(text: str) -> str:
        res = lexicon.analyze(text)
        label = getattr(getattr(res, "sentiment", None), "label", None)
        return getattr(label, "value", label)

    rows: list[dict] = []
    rows.append(_evaluate("lexicon-pipeline", lexicon_predict, GOLD_LABELS, [SEED]))

    trained_predictors: list[tuple[str, Callable[[str], str]]] = []
    for name, cls in (
        ("tfidf-logreg", TfidfSentimentModel),
        ("tfidf-svm", TfidfSvmSentimentModel),
    ):
        try:
            model = cls()
            model.fit([ITEM_TEXTS[i] for i in train_idx], [GOLD_LABELS[i] for i in train_idx])

            def predict_str(t: str, _model=model) -> str:
                pred = _model.predict(t)
                lab = getattr(pred, "label", pred)
                return getattr(lab, "value", lab)

            trained_predictors.append((name, predict_str))
            rows.append(_evaluate(name, predict_str, GOLD_LABELS, [SEED]))
        except Exception as exc:  # noqa: BLE001 — the comparison must degrade honestly
            rows.append({"model": name, "error": repr(exc)})

    trained_any = [r for r in rows if "accuracy" in r and r["model"].startswith("tfidf")]
    best = max(trained_any, key=lambda r: r["accuracy"]) if trained_any else None
    lex_row = next(r for r in rows if r.get("model", "").startswith("lexicon"))
    if best:
        rows.append({
            "model": "delta_accuracy_best_trained_vs_lexicon",
            "delta_accuracy": round(best["accuracy"] - lex_row["accuracy"], 4),
            "interpretation": (
                "positive = the trained model beats the lexicon on held-out assisted "
                "labels; a small positive delta does not close the credibility gap "
                "(labels are model-assisted, review pending)"
            ),
        })

    # Curated-only surface: hand-style, non-templated eval items. Small n —
    # wide CIs — but no frame-sharing with the templated majority.
    curated_rows: list[dict] = []
    if CURATED_EVAL_ITEMS:
        eval_save = list(EVAL_ITEMS)
        for name, predict in [("lexicon", lexicon_predict)] + trained_predictors:
            EVAL_ITEMS[:] = [i for i in eval_save if not items[i]["is_synthetic"]]
            curated_rows.append(_evaluate(f"{name} (curated-only)", predict, GOLD_LABELS, [SEED]))
        EVAL_ITEMS[:] = eval_save

    out = {
        "seed": SEED,
        "fairness": {
            "train_items": len(train_idx),
            "eval_items": len(EVAL_ITEMS),
            "eval_surfaces": "dev + test_random (train excluded; test views untouched)",
            "model_selection": "none - one fixed configuration per family",
            "curated_only_eval_items": len(CURATED_EVAL_ITEMS),
        },
        "seed": SEED,
        "fairness": {
            "train_items": len(train_idx),
            "eval_items": len(EVAL_ITEMS),
            "eval_surfaces": "dev + test_random (train excluded; test views untouched)",
            "model_selection": "none - one fixed configuration per family",
        },
        "caveats": [
            (
                "IN-DISTRIBUTION COMPARISON: 895/1004 gold items come from "
                "deterministic template frames, and train/eval share those frames. "
                "The TF-IDF numbers are therefore an UPPER BOUND (frame "
                "memorisation inflates them), not a field estimate. They show the "
                "trained family can learn Nigerian financial phrasing that the "
                "lexicon missed, and the gap-vs-lexicon is real — but only fresh, "
                "human-confirmed, non-templated labels can bound real-world "
                "accuracy. The curated-only rows on the full eval surfaces are "
                "the honest signpost, at small n."
            ),
            "Kappa here is agreement between assisted labels and each system, "
            "not inter-annotator agreement.",
        ],
        "rows": rows,
        "curated_only_rows": curated_rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print("| model | n | accuracy [CI95] | macro-F1 | kappa |")
    print("|---|---|---|---|---|")
    for r in rows:
        if "delta_accuracy" in r and "accuracy" not in r:
            print(f"| {r['model']} | — | {r['delta_accuracy']:+.4f} | — | — |")
            continue
        if "accuracy" not in r:
            print(f"| {r.get('model', '?')} | — | ERROR: {r.get('error', '')[:60]} | — | — |")
            continue
        print(
            f"| {r['model']} | {r['n']} | {r['accuracy']:.4f} "
            f"[{r['accuracy_ci95'][0]:.4f}-{r['accuracy_ci95'][1]:.4f}] "
            f"| {r['macro_f1']:.4f} | {r['kappa_vs_assisted_labels']:.4f} |"
        )
    print(f"\nwrote {REPORT_PATH}\n")
    if curated_rows:
        print("Curated-only eval surface (hand-style items; small n, wide CI):\n")
        print("| model (curated-only) | n | accuracy [CI95] | macro-F1 | kappa |")
        print("|---|---|---|---|---|")
        for r in curated_rows:
            if "accuracy" not in r:
                print(f"| {r.get('model', '?')} | — | ERROR: {r.get('error', '')[:60]} | — | — |")
                continue
            print(
                f"| {r['model']} | {r['n']} | {r['accuracy']:.4f} "
                f"[{r['accuracy_ci95'][0]:.4f}-{r['accuracy_ci95'][1]:.4f}] "
                f"| {r['macro_f1']:.4f} | {r['kappa_vs_assisted_labels']:.4f} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
