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

## CI evaluation gates (two, with different jobs)

`scripts/eval_gate.py --gate all` runs **two** committed gates:

### 1. `golden` — the demo-path gate (plumbing only)

12 handwritten sentences, baseline `research/baselines/golden_baseline.json`
(accuracy 0.6667, tolerance 0.02). One error moves accuracy by 8.3 points, so
this gate **cannot** catch a single regression — it is a smoke test for the
deterministic demo path, and is labelled as such wherever it appears.

### 2. `goldset` — the quality gate (model-assisted, honestly declared)

`data/annotation/gold/gold_set.jsonl` — **1,004 labelled items** (93
hand-style curated sentences + ~900 deterministically generated items marked
`is_synthetic`, all tagged with coverage markers). Regenerate with
`python scripts/build_gold_set.py`; the data is committed so the gate is
reproducible from git alone.

Baseline `research/baselines/goldset_baseline.json` (frozen):

| Metric | Value |
|---|---|
| n | 1,004 |
| accuracy | 0.4303 (CI95 0.399–0.459) |
| macro-F1 (4 labels) | 0.3524 |
| Cohen's kappa vs system | 0.2551 |

**Read the kappa correctly.** All labels carry `annotator = model-assisted-glm`
and `model_prelabel = true`: an LLM-assisted pass produced them and *no human
has confirmed any label*. The kappa is the chance-corrected agreement between
the assisted labels and the lexicon system — **not** inter-annotator
agreement. The manifest records `inter_annotator_kappa: null`. The review
protocol (two human annotators, real kappa, adjudication) is in
`data/annotation/gold/README.md` and remains the top credibility TODO.

The breakdown is where the value is — the lexicon baseline is weakest exactly
where the roadmap predicted:

| Weakest markers | Accuracy |
|---|---|
| pidgin (both subsets) | 0.13–0.15 |
| mna | 0.20 |
| templated policy/circular | 0.22 |
| headline fragments (both subsets) | 0.24 |
| capital raise / rates / circular | 0.25 |

Strongest: `kobo_format` 1.00, `calendar_dates` 1.00, `trn_bn_abbrev` 0.71,
`dividend` 0.70. Honest summary: the lexicon handles dividend-format naira
amounts but is nearly blind to Pidgin and reads most headline fragments as
neutral. These are the documented gaps a trained model must close.

### Split sizes, stated plainly

The pool is split with `naijafinsent.annotation.splits` (seed 7). The flat
per-item split comes from the random view; held-out views are stored per item.
`test_source` holds out a style family, and `test_time` holds out a synthetic
month, because the gold set has no real publishers or dates yet — both are
declared synthetic per item.

| Split | Items |
|---|---|
| train | 605 |
| dev | 133 |
| test_random | 124 |
| test (frozen view) | 173 |
| test_source (held-out family view) | 190 |
| test_time (held-out month view) | 432 |

**Every locked split holds real labelled items now** — the plain claim "the
splits only matter once labels exist" is answered: they exist, with the
machine-assisted caveat attached.

### Gate mechanics

Tolerance 0.02. A drop in gated accuracy fails CI; refreshing a baseline is an
explicit `--write-baseline` commit. If the committed gold set size differs
from the baseline's `n`, the gate warns (and the baseline must be refreshed as
a reviewed commit).

## Rule-based extractor measurement (per type, with CIs)

`scripts/measure_extractors.py` measures the rule-based NER and event
extractors against the gold set (— the roadmap requirement "measure the
rule-based NER/event extractors per-type P/R with CIs; event recall
prioritised"). Committed report: `research/reports/extractor_metrics.json`.
Nothing in it feeds back into the lexicon — measurement only.

Event extraction (item-level matching; recall is the priority metric because
an event the pipeline misses can never be tracked):

| event type | n_gold | recall [CI95] | precision [CI95] |
|---|---|---|---|
| earnings | 198 | 0.74 [0.68–0.80] | 0.95 [0.92–0.99] |
| dividend | 162 | 0.58 [0.51–0.66] | 0.96 [0.92–0.99] |
| cbn_policy | 70 | **0.17** [0.09–0.27] | 0.92 [0.77–1.00] |
| regulatory_sanction | 94 | 0.79 [0.69–0.87] | **0.48** [0.40–0.55] |
| mna | 58 | 0.36 [0.24–0.50] | 0.95 [0.82–1.00] |
| capital_raise | 41 | 0.78 [0.66–0.90] | 0.74 [0.60–0.88] |
| fx_move | 69 | 0.86 [0.77–0.93] | 0.97 [0.92–1.00] |
| oil_energy | 0 | — | 0.00 (24 predicted, all unsupported) |

Reading the table honestly:

- **cbn_policy recall is the product-blocking gap** (0.17): the keyword model
  fires only when explicit CBN-policy vocabulary appears; templated MPC
  sentences without "CBN/MPC " keywords are missed. The regulator tracker
  must not trust the stub extractor until this is fixed or stated in the UI.
- **regulatory_sanction precision is 0.48** — half of what the pipeline calls
  a sanction event is not one in gold (the "sanction/freeze" vocabulary fires
  on unrelated policy sentences).
- `oil_energy` fires 24 times with zero gold support — a pure false-positive
  class on this gold set; every surfaced "oil_energy event" is suspect until
  the trigger list is tightened.
- NER (surface-form match within the same item; gold records entity *text*,
  not offsets, and ORG/TICKER are measured as one organisation class):
  ORG/TICKER recall 0.88 [0.76–0.97], REGULATOR recall 0.86 [0.57–1.00] — but
  overall entity-level precision is **not meaningful** yet because only ~33
  gold items carry entity annotations: almost every predicted span counts as
  unsupported even when correct. Widening gold entity coverage is a review-
  protocol task, not a code task.

## Experiment map (E1-E9)

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

The committed baselines are the deterministic lexicon model
(`naija-lexicon-sentiment v0.1.0`): 43% accuracy (kappa 0.26) on the 1,004-item
model-assisted gold set, with Pidgin and headline fragments nearly blind — all
of it visible in `research/baselines/goldset_baseline.json` instead of hidden.
Entity-targeted sentiment is **declared as sentence-level scope** (see below)
until aspect-based modelling ships. Trained TF-IDF/transformer variants exist
behind `pip install -e ".[ml]"` and the evaluation runner evaluates whatever
the registry exposes.

## Sentiment target: what we claim to measure

Until aspect-based sentiment ships (a roadmap item, not a shipped feature),
every sentiment label in the API, web app, and benchmark means **sentence-level
coverage tone** — the polarity of the sentence as a whole from the perspective
of the covered company/regulator — and is labelled nowhere as "investor
sentiment". Where one sentence carries opposing polarity for two entities
("Zenith's profit falls as GTCO gains"), the gold set records per-entity labels
in `entity_sentiments` (`entity_paired` marker, ~50 examples) so an
entity-targeted model can be trained the moment the credibility work upholds
the labels.
