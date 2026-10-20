# Case Study — NaijaFinSent

A portfolio write-up of shipping a Nigeria-focused financial NLP platform with
an open benchmark. The narrative is written as if the work shipped; **every
measured number is left as a clearly marked placeholder**, with a note naming
the script that produces it.

> Not investment advice. NaijaFinSent measures language in published coverage;
> it makes no causal or predictive claim about prices or returns.

---

## 1. The problem

Nigerian financial journalism is not US or EU financial journalism with
different names. It is a distinct register: naira-denominated macro language
("MPR", "FX window", "ways and means"), a dense acronym and ticker vocabulary
("CBN", "NGX", "GTCO", "DANGCEM", "MTNN"), frequent Pidgin and code-switched
phrasing, and entity mentions that collide across registers — the ticker
`FCMB` and the bank "FCMB"; "Access" as a bank and as a common word.

Generic and finance-domain NLP models were trained elsewhere. General-purpose
LLMs are fluent but unverifiable: they give a label with no evidence span and
no provenance. For a newsroom analyst, a researcher, or a developer building
on top, "a label with no source sentence" is not usable.

There was no open, provenance-tracked, locally annotated benchmark for
Nigerian financial NLP. Without one, quality claims are not comparable and
errors cannot be attributed.

**Research question:** how much do Nigeria-specific language and entity-aware
modelling improve sentiment, NER, and event extraction over general-purpose
models, few-shot LLMs, and finance-domain baselines?

## 2. Why Nigeria-specific NLP is non-trivial

- **Naira / macro language.** Direction depends on stance. An MPR hike is
  hawkish for inflation but bearish for borrowers; a document classifier that
  learned "rate hike = bad" elsewhere mislabels it here.
- **Pidgin and code-switching.** "Naira don fall" carries sentiment that a
  standard English model reading "naira has fallen" may invert or flatten.
- **Acronym density.** CBN, SEC, NDIC, NERC, FCCPC, PENCOM, NGX, MPR, FX,
  PMS. Tokenizers fragment them and embeddings rarely distinguish them.
- **Ticker collisions.** `ACCESS`, `FCMB`, `UBA`, `ZENITH` are both symbols and
  ordinary words or brand fragments, so NER and entity resolution fight the
  same surface form.
- **Official vs coverage.** A CBN circular and a report *about* it are
  different texts with the same entities and different stance.

## 3. What was built

| Layer | What shipped |
|---|---|
| Corpus | Provenance-tracked Nigerian financial news + official releases, from audited sources |
| Annotation | Four tasks, LLM pre-label + mandatory human review, agreement measured |
| Models | Document sentiment, entity-level sentiment, NER, event classification |
| Entity layer | Resolution (alias / fuzzy / embedding / ambiguous) |
| Intelligence | Event dedup, timelines, novelty, narrative shifts |
| Benchmark | NaijaFin-Bench: splits, baselines, metrics, leaderboard |
| App | FastAPI + worker + React: news, entities, events, model lab, playground |
| Copilot | Retrieval-based, with citations and abstention |

Every prediction links to a source evidence span and a `ModelRef`
(name/version/calibrated). The core is framework-free, enforced by an
architecture test.

## 4. Research design (E1–E9)

| ID | Question |
|---|---|
| E1 | Do local models beat generic, finance-domain, and LLM baselines? |
| E2 | Does entity-aware modelling beat document-only (the delta)? |
| E3 | How does NER perform across families and slices? |
| E4 | How accurate is entity resolution, and does it handle ambiguity honestly? |
| E5 | How much does performance drop across publishers (source-held-out)? |
| E6 | How much does it drop across time (time-held-out)? |
| E7 | What is the latency/memory/calibration cost? |
| E8 | What failure modes recur in error analysis? |
| E9 | Which features/preprocessing/label choices actually matter (ablations)? |

Locked splits: `test_random`, `test_source`, `test_time`. Duplicates and
syndicated copies live in exactly one split. Test labels are frozen.

## 5. What was measured

All values below are **placeholders** pending the experiment runs.

| Result | Value | Produced by |
|---|---|---|
| Document sentiment macro-F1 (`test_random`) | `<!-- TODO(measure): fill after E1 -->` | `python -m naijafinsent.evaluation.runner --task sentiment` |
| NER entity-level exact-match F1 (`test_random`) | `<!-- TODO(measure): fill after E3 -->` | `... --task ner` |
| Event macro-F1 (`test_random`) | `<!-- TODO(measure): fill after E4 -->` | `... --task events` |
| E2 entity-vs-document delta | `<!-- TODO(measure): fill after E2 -->` | `research/experiments/e2_entity_vs_document.py` |
| Publisher generalization gap | `<!-- TODO(measure): fill after E5 -->` | `research/experiments/e5_*` |
| Temporal generalization gap | `<!-- TODO(measure): fill after E6 -->` | `research/experiments/e6_*` |
| `/analyze` p95 latency (stub / transformer) | `<!-- TODO(measure): fill after E7 -->` | `research/experiments/e7_*` |
| Inter-annotator agreement (κ, span F1) | `<!-- TODO(measure) -->` | `python -m naijafinsent.cli annotation agreement` |

> **How to fill this in:** run the script in the right-hand column on the
> locked split, copy the mean and CI from `research/reports/`, and paste it
> here. Never edit a placeholder by hand with an estimate.

## 6. What surprised us

`<!-- TODO(measure): fill after E1–E9 — write the real finding here. -->

Guidance for what belongs here (do not invent it):

- Which baseline punched above its weight (e.g. TF-IDF tying a fine-tuned
  transformer on short headlines).
- Whether the E2 entity-aware delta was positive, near zero, or negative.
- Whether the publisher gap dwarfed the model-choice gap.
- Whether AfroXLM-R helped once the language composition was accounted for.
- Which failure mode dominated error analysis (E8).`

## 7. Engineering decisions

1. **Framework-free core.** `naijafinsent/` depends only on pure-Python and
   Pydantic contracts; the API depends on the core, never the reverse. An
   architecture test (`tests/test_architecture.py`) enforces this, so the core
   stays testable and the serving stack remains swappable.
2. **Provenance and error attribution.** Every pipeline stage records
   success/failure and duration (`StageProvenance`), and `ProcessingStatus` can
   be `partial`, so a failure is attributed to parsing, NER, resolution,
   sentiment, events, or entity sentiment — not reported as a generic error.
3. **Evidence on every prediction.** `EvidenceSpan` and `ModelRef` are part of
   the schema, not an afterthought, so the API and UI cannot show a prediction
   without its source sentence and model version.
4. **Eval-regression gate.** CI re-runs locked-split evaluation and fails the
   build if a metric drops beyond tolerance, so a "small" change cannot
   silently degrade the benchmark.
5. **Deterministic stub fallback.** The API runs offline with `StubPipeline`,
   so every endpoint is testable without models, network, or API keys.
6. **Honest limitations in the payload.** `AnalysisResult.limitations` travels
   with every response and the UI must display it.

## 8. Lessons learned

- The benchmark *is* the contribution. Comparability and error attribution
  matter more than any single model's score.
- Provenance discipline pays off late: when a number looked wrong, stage-wise
  provenance told us whether it was parsing, NER, or the classifier.
- "Uncertain" is a real class in Nigerian macro coverage; collapsing it into
  "neutral" would have hidden the most interesting failures.
- LLM pre-labelling accelerates annotation but must be flagged and reviewed;
  treating pre-labels as gold would have made the benchmark circular.
- Generalization gaps across publishers and time are at least as important as
  the headline random-split score.
- Afro-centric models are not a free win; they need local-language content to
  have anything to model.

## 9. Portfolio statement (ready to use)

> Built NaijaFinSent, a Nigeria-focused financial NLP platform with an open
> benchmark. I compared TF-IDF, finance-domain, fine-tuned transformer, and
> LLM baselines for sentiment, NER, and event extraction on locally annotated
> data, evaluated generalization across publishers and time, and shipped a
> full-stack app that links every prediction to source evidence.

Supporting detail to add once measured:

- Corpus: `<!-- TODO(measure): article count, publisher count -->`
- Annotations: `<!-- TODO(measure): item count, agreement scores -->`
- Headline results: `<!-- TODO(measure): macro-F1 per task, E2 delta -->`
- Generalization: `<!-- TODO(measure): source/time gaps -->`
- App: `<!-- TODO(measure): p95 latency -->`
