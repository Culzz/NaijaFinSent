# Evaluation

## Metrics discipline

- **Macro-F1 over the declared label space** is the headline sentiment metric.
  Absent-but-declared classes contribute 0 so `uncertain` is never drowned out
  (`naijafinsent/evaluation/metrics.py`, `DEFAULT_LABELS`).
- Every reported metric carries a **bootstrap confidence interval** (seeded,
  documented `n`). Point estimates alone are never quoted as findings.
- **Slices** (publisher, topic, length, period) are reported with counts and
  low-support flags; small slices show wider CIs and must not be quoted alone.
- **Seeds and variance** are recorded for every run; results are reproducible
  from a fixed seed on a fixed split.

## The locked test split is never tuned on

Split manifests are hashed and guarded by tests (`tests/test_locked_guard.py`).
Model selection, hyperparameters, thresholds, and prompt tweaks happen on the
dev split only. Touching the test split for tuning is treated as benchmark
fraud in the codebase's own terms: the guard fails the run.

## NaijaFin-Bench

The benchmark bundles annotated records with per-source redemption policy
(`naijafinsent/bench.py`): labels and URLs are redistributable; article text is
not. Three views ship — sentiment, NER, events — plus a manifest for rebuild.

## CI eval regression gate

`scripts/eval_gate.py` runs a **committed golden set** of Nigerian financial
sentences through the deterministic pipeline and compares accuracy against the
frozen baseline `research/baselines/golden_baseline.json`:

```
golden accuracy: 8/12 = 0.6667      (declared in the baseline)
tolerance: 0.02                     (CI fails if accuracy drops below)
```

The gate protects the *offline demo path* from silent regressions. It is small
and deterministic on purpose — research-grade models are evaluated on the locked
split, not on this gate. Baselines are refreshed explicitly with
`--write-baseline`, and every refresh is a reviewed commit.

## Experiment map (E1–E9)

| # | Question |
|---|---|
| E1 | Do Nigeria-specific lexicons beat generic finance lexicons? |
| E2 | Does entity-aware NER beat generic NER on Nigerian text? |
| E3 | Do local events need event-type priors? |
| E4 | Event dedup: blending shingles with editorial (unigram) distance |
| E5 | Entity resolution with and without ticker-collision context |
| E6 | Calibration: temperature scaling before quoting confidence |
| E7 | Slices: where do models break (publisher, topic, register)? |
| E8 | LLM zero/few-shot vs fine-tuned local models |
| E9 | End-to-end timeline quality: two-clock discipline under ingest noise |

Results land in `research/reports/` as build artifacts; committed baselines in
`research/baselines/` are the only research state that travels in git.

## Known honest limitations

The current committed baseline is a small deterministic lexicon model
(`naija-lexicon-sentiment v0.1.0`, 8/12 on the golden set). Its misses are
lexicon-coverage limitations (see `docs/MODEL_CARD.md`) — documented, not
over-tuned away. Trained TF-IDF/transformer variants exist behind
`pip install -e ".[ml]"` and the evaluation runner evaluates whatever the
registry exposes.
