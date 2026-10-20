# Model Card — NaijaFinSent Model Stack

One card, with a per-task section. Every model in the stack follows the same
contracts: predictions carry a `ModelRef` (`name`, `version`, `task`,
`calibrated`) and, wherever meaningful, `EvidenceSpan`s.

> **All metric values below are placeholders.**
> Each is produced by a named script. No number is quoted until measured.
> See `docs/EVALUATION.md` and `docs/DATA_CARD.md` for the data behind them.

---

## 0. Overview

| Field | Value |
|---|---|
| Tasks | Document sentiment, entity-level sentiment, NER, event classification, entity resolution |
| Task names (registry) | `sentiment`, `entity_sentiment`, `ner`, `events` |
| Language | English (Nigerian English); Pidgin/code-switching observed but under-represented |
| Domain | Nigerian financial news and official releases |
| Serving contract | `naijafinsent/inference/pipeline.py` (`AnalysisPipeline`), inputs/outputs in `naijafinsent/schemas.py` |
| Framework-free core | Yes — the API depends only on the pipeline and schemas |

### 0.1 HuggingFace model naming convention

Published models use:

```
Culzz/naijafinsent-<task>-<arch>-<date>
```

Examples:

- `Culzz/naijafinsent-sentiment-deberta-v3-base-YYYYMMDD`
- `Culzz/naijafinsent-ner-distilbert-base-YYYYMMDD`
- `Culzz/naijafinsent-events-deberta-v3-base-YYYYMMDD`
- `Culzz/naijafinsent-entity-sentiment-deberta-v3-base-YYYYMMDD`

Rules: lowercase, hyphen-separated, `<task>` from the registry task names,
`<arch>` a short architecture slug, `<date>` the release date `YYYYMMDD`. The
matching `ModelRef.version` in the registry should equal the release tag.

`<!-- TODO: confirm HuggingFace org/user handle before first public push -->`

### 0.2 The honest note on AfroXLM-R

**AfroXLM-R only helps if local-language content is actually present.** The
corpus is near-exclusively English. If the corpus contains little Pidgin,
Yoruba, Hausa, or Igbo financial text, Afro-centric encoders have no signal to
exploit and will match — not beat — English-domain models. Any claim that
AfroXLM-R "improves Nigerian financial NLP" must be conditioned on a
language composition measured from the corpus (`corpus stats`), and tested on
a slice where local-language content exists. Absent that slice, report the
result as "no measurable advantage", not a win.

---

## 1. Task: Document sentiment

### 1.1 Model family and baselines

| Model | Family | Notes |
|---|---|---|
| TF-IDF + Logistic Regression | Classical | Word/char n-grams; strong, cheap baseline |
| TF-IDF + SVM | Classical | Linear SVM; calibrate for probabilities |
| FinBERT (zero-shot) | Finance-domain | No fine-tuning; tests domain transfer |
| Few-shot LLM | LLM | Prompted, few examples; no training |
| DistilBERT (fine-tuned) | General transformer | Small, fast |
| DeBERTa-v3-base (fine-tuned) | General transformer | Stronger encoder |
| FinBERT (fine-tuned) | Finance-domain | Domain pretraining + fine-tuning |
| AfroXLM-R (fine-tuned) | Afro-centric multilingual | Only meaningful with local-language content (§0.2) |

### 1.2 Intended use
Classify the sentiment of a Nigerian financial news article or release into
{positive, negative, neutral, uncertain}. `uncertain` is distinct from
`neutral`.

### 1.3 Out-of-scope use
Investment advice; trading signals; causal or predictive claims about prices
or returns; scoring private individuals; any use outside published financial
coverage.

### 1.4 Training data and split
`docs/DATA_CARD.md`. Locked splits: `train`, `dev`, `test_random`,
`test_source`, `test_time`. Test labels are frozen. Never tune on the locked
test sets.

### 1.5 Evaluation metrics and slices
- **Primary:** macro-F1 over 4 labels on each test split.
- **Also:** per-class F1, confusion matrix, accuracy.
- **Slices:** publisher, topic, article length band, period (`test_random`);
  publisher-held-out (`test_source`); time-held-out (`test_time`).

| Split | Macro-F1 | Produced by |
|---|---|---|
| `test_random` | `<!-- TODO(measure): fill after E1 -->` | `python -m naijafinsent.evaluation.runner --task sentiment --split test_random` |
| `test_source` | `<!-- TODO(measure): fill after E5 -->` | `... --split test_source` |
| `test_time` | `<!-- TODO(measure): fill after E6 -->` | `... --split test_time` |

Per-slice tables: `<!-- TODO(measure): publisher/topic/length slices -->`.

### 1.6 Calibration status
Raw probabilities by default; temperature scaling fitted on `dev` and recorded
via `ModelRef.calibrated=true` when applied. Calibration on unseen publishers
is a known weak point.

`<!-- TODO(measure): ECE and reliability diagram before/after scaling, on
test_random and test_source; script: research/experiments/e7_* -->`

### 1.7 Cost, latency, memory
| Model | Latency (CPU, per article) | Memory | Marginal cost |
|---|---|---|---|
| TF-IDF + LR/SVM | `<!-- TODO(measure) -->` | small | 0 |
| DistilBERT | `<!-- TODO(measure) -->` | medium | 0 |
| DeBERTa-v3-base | `<!-- TODO(measure) -->` | medium | 0 |
| FinBERT | `<!-- TODO(measure) -->` | medium | 0 |
| Few-shot LLM | `<!-- TODO(measure) -->` | n/a | per-token API cost |
| AfroXLM-R | `<!-- TODO(measure) -->` | large | 0 |

Measurement harness: `research/experiments/e7_*` <!-- verify against --help -->.

### 1.8 Limitations
Sarcasm and irony; mixed sentiment in one article; naira/macro language where
direction depends on stance (e.g. MPR hikes); Pidgin; abbreviations; domain
shift across publishers and time; class imbalance (`uncertain` is rare);
annotation provenance (some labels began as LLM pre-labels — see data card
§4.1). See `docs/LIMITATIONS.md` for the full treatment.

---

## 2. Task: Entity-level sentiment

### 2.1 Model family and baselines
Same families as §1.1, applied to a target entity's context window; plus a
document-sentiment transfer baseline (assign document sentiment to the
target entity) as the honest "is entity-awareness worth it?" comparison.

### 2.2 Intended use
Sentiment toward a specific entity (company, bank, regulator) within an
article, with a `rationale_span`.

### 2.3 Out-of-scope use
As above (§1.3). Also: sentiment toward an entity mentioned only in passing
with no informative context — the model should abstain or return low
confidence, not guess.

### 2.4 Training data and split
`docs/DATA_CARD.md`. Entity-level labels are sparser than document labels;
`<!-- TODO(measure): entity_sentiment label counts -->` via
`python -m naijafinsent.cli annotation stats` <!-- verify against --help -->.

### 2.5 Evaluation metrics and slices
Per-entity macro-F1; evidence-span overlap; and the **E2 delta** — the
improvement of entity-aware event extraction over document-only.

| Metric | Value | Produced by |
|---|---|---|
| Entity-level macro-F1 (`test_random`) | `<!-- TODO(measure): fill after E2 -->` | `python -m naijafinsent.evaluation.runner --task entity_sentiment` |
| E2 entity-vs-document delta | `<!-- TODO(measure) -->` | `research/experiments/e2_entity_vs_document.py` |

### 2.6 Calibration status
Raw unless temperature-scaled; `ModelRef.calibrated` records which.

### 2.7 Cost, latency, memory
Scales with number of entities per article: `<!-- TODO(measure) -->` per
entity.

### 2.8 Limitations
Context windows can merge multiple entities' sentiment; a single sentence can
express opposite sentiment about two entities; target-boundary ambiguity;
sparse labels. Plus all §1.8 limitations.

---

## 3. Task: Named-entity recognition (NER)

### 3.1 Model family and baselines
| Model | Family |
|---|---|
| Regex + lexicon (rule) | Deterministic baseline for REGULATOR, TICKER, CURRENCY |
| CRF | Classical sequence labelling |
| DistilBERT (fine-tuned) | General transformer token classification |
| DeBERTa-v3-base (fine-tuned) | Stronger general transformer |
| FinBERT (fine-tuned) | Finance-domain |
| AfroXLM-R (fine-tuned) | Afro-centric; only with local-language content (§0.2) |
| Few-shot LLM | Prompted span extraction |

### 3.2 Intended use
Extract spans and types over the 8 entity types (`constants.py`
`ENTITY_TYPES`): ORG, PER, REGULATOR, MONEY, TICKER, CURRENCY, SECTOR,
EVENT_TRIGGER. Exactly one primary type per span.

### 3.3 Out-of-scope use
Entity linking to external knowledge graphs beyond our alias table; extraction
from non-financial text; PII extraction from private data.

### 3.4 Training data and split
`docs/DATA_CARD.md`; locked splits as §1.4. Double-annotated subset supports
span-level F1 agreement.

### 3.5 Evaluation metrics and slices
- **Primary:** entity-level **exact-match F1** (strict span boundaries + type),
  seqeval-style.
- **Slices:** by entity type, publisher, length, period, and on
  `test_source`/`test_time`.

| Split | Entity-level exact-match F1 | Produced by |
|---|---|---|
| `test_random` | `<!-- TODO(measure): fill after E3 -->` | `python -m naijafinsent.evaluation.runner --task ner --split test_random` |
| `test_source` | `<!-- TODO(measure): fill after E5 -->` | `... --split test_source` |
| `test_time` | `<!-- TODO(measure): fill after E6 -->` | `... --split test_time` |

Per-type F1: `<!-- TODO(measure) -->`.

### 3.6 Calibration status
Span confidence is model-provided, not calibrated; treat as ranking, not
probability. `ModelRef.calibrated` remains false for NER.

### 3.7 Cost, latency, memory
`<!-- TODO(measure): per-article latency/memory for each NER model -->`
(harness: `research/experiments/e7_*`).

### 3.8 Limitations
Unseen entities and novel tickers; abbreviation and acronym density (CBN, SEC,
NGX, MPR, GTCO); ticker-vs-word collisions (`ACCESS`, `FCMB`); boundary
ambiguity in nested names; REGULATOR-vs-ORG decisions; MONEY without a stated
unit; domain shift; annotation provenance. All §1.8 limitations apply.

---

## 4. Task: Event classification

### 4.1 Model family and baselines
| Model | Family |
|---|---|
| TF-IDF + LR/SVM (multi-label) | Classical |
| Rule/keyword triggers | Deterministic baseline |
| DistilBERT / DeBERTa-v3 (fine-tuned) | Transformer multi-label |
| FinBERT (fine-tuned) | Finance-domain |
| Entity-aware transformer (document + entity features) | Tests RQ2 |
| Few-shot LLM | Prompted event typing |

### 4.2 Intended use
Assign zero or more of the 8 event types
(`constants.py` `EVENT_TYPES`): cbn_policy, earnings, dividend, mna,
regulatory_sanction, capital_raise, fx_move, oil_energy. Attach
`event_date` when stated and an `evidence_span`.

### 4.3 Out-of-scope use
Price prediction; event *impact* estimation; forecasting event frequency.

### 4.4 Training data and split
`docs/DATA_CARD.md`; locked splits as §1.4. Multi-label; `event_date` is the
event date, not publish date.

### 4.5 Evaluation metrics and slices
- **Primary:** per-class F1 and macro-F1 over the 8 types (multi-label).
- **Entity-aware ablation:** document-only vs entity-aware (E2).
- **Slices:** event type, publisher, period, and `test_source`/`test_time`.

| Metric | Value | Produced by |
|---|---|---|
| Macro-F1 (`test_random`) | `<!-- TODO(measure): fill after E4 -->` | `python -m naijafinsent.evaluation.runner --task events --split test_random` |
| E2 entity-aware delta | `<!-- TODO(measure) -->` | `research/experiments/e2_entity_vs_document.py` |
| `test_source` / `test_time` | `<!-- TODO(measure): fill after E5/E6 -->` | `... --split test_source` / `--split test_time` |

### 4.6 Calibration status
Multi-label probabilities are raw unless calibrated per label; `ModelRef`
records the flag.

### 4.7 Cost, latency, memory
`<!-- TODO(measure) -->`.

### 4.8 Limitations
Class imbalance (rare types under-represented); overlapping event types in one
article; unstated `event_date`; trigger ambiguity across domains; boundary
between `cbn_policy` and `fx_move`; `oil_energy` vs general energy news; domain
shift; annotation provenance. All §1.8 limitations apply.

---

## 5. Task: Entity resolution

### 5.1 Method and comparison
- **Alias table** — exact known aliases (e.g. "GTCO" ↔ "Guaranty Trust Holding").
- **Fuzzy** — `rapidfuzz` string similarity.
- **Embedding** — vector similarity for surface variation.
- **Ambiguous** — when methods disagree or confidence is low, return
  `entity_id=null`, `resolution_method="ambiguous"` rather than guess.

### 5.2 Intended use
Map entity mentions to canonical entities so events, timelines, and sentiment
aggregate correctly.

### 5.3 Out-of-scope use
Authoritative entity authority records; resolving entities outside our curated
alias table with high confidence.

### 5.4 Evaluation
Resolution accuracy / F1 on a held-out set of mention→canonical pairs;
ambiguous-case detection rate.

`<!-- TODO(measure): resolution accuracy, ambiguous rate; script:
research/experiments/e4_* or the entity_resolution eval -->`

### 5.5 Limitations
Ticker/word collisions; same-name distinct entities; corporate-name changes;
subsidiary vs parent; incomplete alias table. Errs toward `ambiguous`, which
is honest but reduces recall. See `docs/LIMITATIONS.md`.

---

## 6. Overall limitations

- **Sarcasm and mixed sentiment** defeat document-level classifiers.
- **Naira/macro language** where direction is stance-dependent.
- **Pidgin and local registers** under-represented → no strong local-language
  claim (§0.2).
- **Unseen entities and abbreviations** in NER and resolution.
- **Domain shift** across publishers and over time; measured as the
  `test_source`/`test_time` gaps (`docs/EVALUATION.md`, E5/E6).
- **Class imbalance** for rare sentiment and event classes.
- **Annotation provenance:** some labels began as LLM pre-labels and were
  human-reviewed (data card §4.1); provenance is flagged and must be reported.
- **Calibration** on unseen publishers is weak.

## 7. Ethical considerations and financial-misuse risk

- Outputs are **not investment advice** and carry no causal or predictive
  claim. Disclaimers are set in `config.py` and surfaced by the API and UI.
- The principal misuse risk is a reader acting on sentiment as if it were a
  signal. Mitigations: evidence spans on every prediction, persistent
  disclaimers, `AnalysisResult.limitations` rendered in the UI, and copilot
  abstention when evidence is absent.
- No profiling of private individuals; entities are public figures and
  organisations in published news.

## 8. Recommended citation and usage disclaimer

```
NaijaFinSent contributors (2026). NaijaFinSent: a Nigeria-focused financial
NLP and event-intelligence platform with the NaijaFin-Bench benchmark.
https://github.com/Culzz/NaijaFinSent
```

Usage disclaimer to reproduce wherever outputs are shown:

> NaijaFinSent measures language in published news coverage. It is not
> investment advice and makes no causal or predictive claims about prices or
> returns. Predictions are model estimates, may be miscalibrated on unseen
> publishers, and every prediction links to the source text and its evidence
> span.

## 9. How to fill in the numbers

| Section | Producing script |
|---|---|
| §1.5 sentiment metrics | `python -m naijafinsent.evaluation.runner --task sentiment` |
| §2.5 entity sentiment + E2 | `research/experiments/e2_entity_vs_document.py` |
| §3.5 NER metrics | `python -m naijafinsent.evaluation.runner --task ner` |
| §4.5 event metrics | `python -m naijafinsent.evaluation.runner --task events` |
| §5.4 resolution metrics | `research/experiments/e4_*` <!-- verify against --help --> |
| Generalization (E5/E6) | `research/experiments/e5_*`, `e6_*` <!-- verify against --help --> |
| Latency/memory/calibration (E7) | `research/experiments/e7_*` <!-- verify against --help --> |
| Error analysis (E8), ablations (E9) | `research/experiments/e8_*`, `e9_*` <!-- verify against --help --> |
