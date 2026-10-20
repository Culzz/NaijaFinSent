# Software Requirements Specification — NaijaFinSent

| Field | Value |
|---|---|
| Document | Software Requirements Specification (SRS) |
| Product | NaijaFinSent — Nigeria-focused financial NLP and event-intelligence platform |
| Version | 1.0 (Release 1 scope) |
| Status | Draft for implementation |
| Audience | Researchers, ML engineers, reviewers, contributors |

---

## 1. Problem statement

Nigerian financial news is written in a register that general-purpose and
finance-domain NLP models handle poorly. It mixes naira-denominated macro
language ("MPR", "FX window", "ways and means"), a dense acronym and ticker
vocabulary ("CBN", "NGX", "GTCO", "DANGCEM", "MTNN"), frequent Pidgin and
code-switched phrasing, and entity mentions that collide across registers
(the ticker `FCMB` and the bank "FCMB"; "Access" as a bank and as a common
word). Off-the-shelf sentiment tools trained on English financial-news corpora
(US/EU) miss local context, and general-purpose LLMs produce fluent but
unverifiable output with no evidence spans and no provenance.

There is no open, provenance-tracked, locally annotated benchmark for Nigerian
financial NLP. Without one, claims about "state of the art" are not
comparable, error attribution is impossible, and downstream tools cannot be
audited.

## 2. Research question

> How much do Nigeria-specific language and entity-aware modelling improve
> sentiment classification, named-entity recognition (NER), and event
> extraction over general-purpose models, few-shot LLMs, and finance-domain
> baselines?

Sub-questions:

- **RQ1** — Does fine-tuning on Nigerian financial text beat finance-domain
  zero-shot (FinBERT) and general-purpose baselines on document sentiment?
- **RQ2** — Does an entity-aware pipeline improve event extraction over
  document-only classification?
- **RQ3** — How well do models generalize across publishers (source-held-out)
  and across time (time-held-out)?
- **RQ4** — Does local-language modelling (Afro-centric encoders) help, and
  only when local-language content is actually present in the corpus?
- **RQ5** — Can LLM pre-labelling plus mandatory human review produce usable
  training data at a fraction of the annotation cost, without inflating
  apparent quality?

## 3. Scope

NaijaFinSent builds and evaluates a Nigeria-focused financial NLP stack:

- A provenance-tracked corpus of Nigerian financial news and official
  releases, built from audited sources.
- Locally annotated labels for four tasks: document sentiment, entity-level
  sentiment, NER, and event extraction; plus an entity-resolution layer.
- A benchmark (NaijaFin-Bench) comparing TF-IDF, finance-domain, fine-tuned
  transformer, and LLM baselines with locked splits and variance reporting.
- Event intelligence: deduplication, event timelines, novelty, and narrative
  shifts.
- A FastAPI service, a worker, and a React app that expose every prediction
  with source evidence and model version.
- A retrieval-based copilot with citations and explicit abstention.

### 3.1 Non-goals (explicit)

The following are **out of scope** and must not be implied by any artifact,
endpoint, UI string, or document:

1. **Not investment advice.** No output may be presented as a recommendation
   to buy, sell, or hold any security or instrument.
2. **No trading signals.** The system does not emit, rank, or schedule trades.
3. **No causal claims about market moves.** The system measures language in
   published coverage; it does not claim that coverage caused a price move.
4. **No forecasting without separate time-aware validation and leakage
   controls.** Any future predictive feature requires its own protocol with
   strict temporal splits and leakage audits, and is out of scope for
   Releases 1–3.
5. **No full-text redistribution of copyrighted articles.** We publish labels,
   URLs, and rebuild scripts, not article bodies, except where a source's
   licence explicitly permits it (see `docs/DATA_CARD.md` and `docs/SOURCES.md`).
6. **No financial, legal, or compliance advice.** Outputs are not audit or
   regulatory filings.
7. **No real-time market data or price feeds.** The corpus is published text,
   not tick data.

## 4. Users and personas

| Persona | Primary job-to-be-done | Key views/endpoints |
|---|---|---|
| **Researcher** | Compare Nigeria-specific models against baselines on a locked, reproducible benchmark, and report variance. | `docs/EVALUATION.md`, `research/experiments/`, `python -m naijafinsent.evaluation.runner` |
| **Newsroom analyst** | Find and verify what was reported about a company, sector, or regulator, with the exact source sentence. | `/events`, `/entities`, `/articles/{id}`, entity/event timelines |
| **Developer / ML engineer** | Add a model or task and integrate the pipeline without breaking the core contract. | `naijafinsent/inference/pipeline.py`, `docs/MODEL_CARD.md`, `CONTRIBUTING.md` |
| **Portfolio reviewer** | Judge engineering and research rigour from docs, tests, and reproducible reports. | `README.md`, `docs/CASE_STUDY.md`, `research/reports/` |
| **Curious public reader** | Understand coverage of a topic with plain-language caveats and evidence. | `/playground`, `/news`, limitations banner from `AnalysisResult.limitations` |

## 5. Functional requirements

One requirement per numbered line, phrased so it can be tested.

### 5.1 Corpus ingestion and provenance (FR-CORPUS)

- **FR-CORPUS-1** — The system shall register every source in a manifest
  (`data/manifests/`) with `source_id`, `base_url`, `url_pattern`,
  `access_method`, `license_note`, `trust_tier`, and `robots_checked_at`.
- **FR-CORPUS-2** — The system shall ingest articles via RSS, sitemap, HTML,
  or API per the source's `access_method`, using only the configured
  `user_agent` and respecting `fetch_rate_limit_seconds`.
- **FR-CORPUS-3** — The system shall enforce `fetch_max_bytes`,
  `fetch_timeout_seconds`, and `fetch_max_redirects` on every fetch and shall
  abort and record failures rather than partial garbage.
- **FR-CORPUS-4** — The system shall store for each article: `url`,
  `canonical_url`, `title`, `publisher`, `published_at`, `fetched_at`,
  `language`, `content`, `content_hash`, and `is_official_release`.
- **FR-CORPUS-5** — The system shall reject non-HTML and non-text responses and
  shall never execute scripts from fetched pages.
- **FR-CORPUS-6** — The system shall block requests to private, loopback, and
  link-local address ranges (SSRF protection) before any fetch.
- **FR-CORPUS-7** — The system shall compute `content_hash` as the SHA-256 of
  normalised content and shall store it on every article.
- **FR-CORPUS-8** — The system shall record ingestion provenance (source,
  timestamps, fetch outcome) such that any article can be traced to its origin
  and fetch event.

### 5.2 Deduplication and canonicalisation (FR-CORPUS)

- **FR-CORPUS-9** — The system shall detect exact duplicates by `content_hash`.
- **FR-CORPUS-10** — The system shall detect near-duplicates using MinHash
  (`minhash_signature`) and shall mark `is_duplicate` and `duplicate_of`.
- **FR-CORPUS-11** — The system shall mark syndicated copies with
  `syndicated_from` pointing at the original `article_id`.
- **FR-CORPUS-12** — The system shall ensure duplicates and syndicated copies
  appear in exactly one split (no cross-split leakage).

### 5.3 Annotation (FR-ANNOT)

- **FR-ANNOT-1** — The system shall export and import annotations in the
  `AnnotationRecord` schema with `item_id`, `article_id`, `split`, `text`,
  `sentiment`, `spans`, `money`, and `events`.
- **FR-ANNOT-2** — The system shall record `annotator` and `model_prelabel` on
  every sentiment and event annotation.
- **FR-ANNOT-3** — The system shall flag every item whose first pass was an LLM
  pre-label and which required mandatory human review (`model_prelabel=true`).
- **FR-ANNOT-4** — The system shall compute inter-annotator agreement: Cohen's
  κ for categorical labels and span-level F1 for NER, over a double-annotated
  sample of 15–20% of items.
- **FR-ANNOT-5** — The system shall validate spans (`end > start`, offsets
  within text) and reject invalid records at import.
- **FR-ANNOT-6** — The system shall freeze labels used for the locked test
  splits behind a split-manifest hash.

### 5.4 Modelling tasks (FR-MODEL)

- **FR-MODEL-1** — The system shall produce document sentiment over
  `SENTIMENT_LABELS` = {positive, negative, neutral, uncertain}, treating
  "uncertain" distinctly from "neutral".
- **FR-MODEL-2** — The system shall produce NER over `ENTITY_TYPES` = {ORG,
  PER, REGULATOR, MONEY, TICKER, CURRENCY, SECTOR, EVENT_TRIGGER}, with a
  single primary type per span.
- **FR-MODEL-3** — The system shall normalise MONEY annotations into
  `value` + ISO `currency` (`NGN`, `USD`, …) and optional `unit`, and shall
  never infer a missing unit.
- **FR-MODEL-4** — The system shall produce event classification over
  `EVENT_TYPES` (8 classes; see §5.5).
- **FR-MODEL-5** — The system shall produce entity-level sentiment with a
  `target_entity` and a `rationale_span`.
- **FR-MODEL-6** — Every model prediction shall carry a `ModelRef` with
  `name`, `version`, `task`, and `calibrated`.
- **FR-MODEL-7** — Every prediction shall carry at least one `EvidenceSpan`
  or explicitly return an empty evidence list with a recorded limitation.

### 5.5 Event intelligence (FR-EVENT)

- **FR-EVENT-1** — The system shall classify each item into zero or more of the
  8 event types: `cbn_policy`, `earnings`, `dividend`, `mna`,
  `regulatory_sanction`, `capital_raise`, `fx_move`, `oil_energy`.
- **FR-EVENT-2** — The system shall record `event_date` as the date the event
  happened, distinct from publish date, when stated.
- **FR-EVENT-3** — The system shall attach an `evidence_span` that justifies
  each event label.
- **FR-EVENT-4** — The system shall deduplicate events across articles so a
  single real-world event is counted once in timelines.
- **FR-EVENT-5** — The system shall build event timelines per event type and per
  entity, ordered by `event_date`.
- **FR-EVENT-6** — The system shall compute novelty (first reportage) and
  narrative-shift signals over time windows.

### 5.6 Entity resolution (FR-MODEL / FR-EVENT)

- **FR-EVENT-7** — The system shall resolve entity mentions to canonical
  entities using alias, fuzzy, and embedding methods, recording
  `resolution_method` ∈ {alias, fuzzy, embedding, ambiguous}.
- **FR-EVENT-8** — The system shall mark genuinely ambiguous mentions as
  `ambiguous` with `entity_id=null` rather than guessing.
- **FR-EVENT-9** — The system shall keep an auditable entity alias table and
  shall expose resolution decisions on demand.

### 5.7 API (FR-API)

- **FR-API-1** — The system shall expose `POST /analyze` returning a full
  `AnalysisResult` for one text, including `limitations` and `latency_ms`.
- **FR-API-2** — The system shall expose a batch endpoint capped at
  `max_batch_size`, rejecting larger payloads.
- **FR-API-3** — The system shall reject text longer than `max_text_chars`
  with a 413/422 and a clear message.
- **FR-API-4** — The system shall expose `GET /health` returning
  `HealthStatus` with `status`, `version`, `database`, `models_loaded`,
  `corpus_size`, and `last_ingestion_at`.
- **FR-API-5** — The system shall expose `GET /models` listing `ModelInfo`
  for every loaded model with metrics and `trained_at`.
- **FR-API-6** — The system shall expose read endpoints for articles,
  entities, events, timelines, and trends, each returning evidence spans.
- **FR-API-7** — The system shall enforce `rate_limit_per_minute` per client
  and return 429 with `Retry-After` when exceeded.
- **FR-API-8** — The system shall include the `disclaimer` string and the
  "not investment advice" notice in the OpenAPI description and every analysis
  response.
- **FR-API-9** — The system shall run without any trained model by falling
  back to the deterministic `StubPipeline`, so all endpoints are testable
  offline.

### 5.8 Frontend (FR-UI)

- **FR-UI-1** — The app shall provide views for news, entities, events,
  model lab, and a playground.
- **FR-UI-2** — Every prediction shown shall render its evidence span(s) and
  the model `name`/`version`.
- **FR-UI-3** — The app shall display the `limitations` list returned by the
  API alongside predictions.
- **FR-UI-4** — The app shall display the "not investment advice" disclaimer
  persistently and on any analysis result.
- **FR-UI-5** — The app shall meet WCAG 2.1 AA for the primary flows
  (contrast, keyboard reachability, focus visibility, labels).

### 5.9 Benchmark (FR-BENCH)

- **FR-BENCH-1** — The system shall publish NaijaFin-Bench: data manifests,
  splits, baselines, metrics, and a leaderboard.
- **FR-BENCH-2** — The system shall compare TF-IDF+LR, TF-IDF+SVM,
  FinBERT zero-shot, few-shot LLM, DistilBERT, DeBERTa-v3, FinBERT
  fine-tuned, and AfroXLM-R on the four tasks.
- **FR-BENCH-3** — The system shall evaluate on random, source-held-out, and
  time-held-out splits and report all three.
- **FR-BENCH-4** — The system shall report variance across ≥3 seeds and
  confidence intervals, not point estimates alone.
- **FR-BENCH-5** — The system shall compute the entity-vs-document delta
  (E2) quantifying the entity-aware gain.
- **FR-BENCH-6** — The system shall report per-slice metrics for publisher,
  topic, length, and period.

### 5.10 Copilot (FR-API / FR-UI)

- **FR-COPILOT-1** — The copilot shall answer using retrieved corpus items
  and shall cite each source it uses.
- **FR-COPILOT-2** — The copilot shall abstain ("insufficient evidence") when
  retrieval does not support an answer, rather than speculate.
- **FR-COPILOT-3** — The copilot shall never present output as advice or a
  forecast, and shall append the standard disclaimer.
- **FR-COPILOT-4** — The copilot shall degrade gracefully when no LLM key is
  configured, returning retrieval results with citations and no generated
  prose.

## 6. Non-functional requirements (NFR)

- **NFR-1 Reproducibility** — Every experiment shall run from a fixed seed set,
  produce variance across ≥3 seeds, and report confidence intervals. Splits
  and manifests shall be hash-pinned.
- **NFR-2 Provenance and error attribution** — Every pipeline stage shall
  record success/failure and duration (`StageProvenance`), so failures are
  attributed to parsing, NER, resolution, sentiment, events, or entity
  sentiment rather than reported as a generic error.
- **NFR-3 Performance/latency** — `POST /analyze` on stub models shall meet
  p95 ≤ 150 ms locally; with a fine-tuned transformer stack, p95 ≤ 2 s on
  CPU for a single article-length text. Targets are provisional pending
  measurement (`<!-- TODO(measure): confirm after E7, via research/experiments/e7_* -->`).
- **NFR-4 Cold start** — The API shall serve `/health` within 5 s of process
  start; full model load shall complete within 60 s on CPU; stub mode shall
  load within 1 s.
- **NFR-5 Security** — The system shall enforce rate limits, payload caps,
  SSRF protection, and secrets hygiene (no keys in code or logs). LLM keys
  shall be optional and never required for inference.
- **NFR-6 Observability** — The system shall log structured events with
  `log_level`, expose `/health`, and record latency per stage.
- **NFR-7 Accessibility** — Primary frontend flows shall meet WCAG 2.1 AA.
- **NFR-8 Cost efficiency** — LLM use shall be confined to the optional
  few-shot baseline and optional copilot prose; all other paths shall run
  locally at zero marginal cost.
- **NFR-9 Licensing/legal** — The system shall store and expose only what a
  source's `license_note` permits, and shall not redistribute article body
  text where it is not permitted.

## 7. Success metrics

Numeric targets marked *provisional* depend on data volume and are fixed after
the first measurement. Every placeholder names the script that produces the
number.

### 7.1 Research metrics

| ID | Metric | Definition | Target | Produced by |
|---|---|---|---|---|
| RM-1 | Sentiment macro-F1 | Macro-averaged F1 over 4 labels, `test_random` | provisional; must beat best non-fine-tuned baseline | `python -m naijafinsent.evaluation.runner --split test_random` |
| RM-2 | NER entity-level exact-match F1 | seqeval-style strict span+type F1 | provisional | `python -m naijafinsent.evaluation.runner --task ner` |
| RM-3 | Event class F1 | Per-class and macro F1 over 8 event types | provisional | `python -m naijafinsent.evaluation.runner --task events` |
| RM-4 | E2 entity-vs-document delta | Event F1 (entity-aware) − Event F1 (document-only) | > 0 to claim entity-aware gain | `research/experiments/e2_entity_vs_document.py` |
| RM-5 | Publisher generalization gap | `test_random` F1 − `test_source` F1 | reported, not gamed | `research/experiments/e5_*` <!-- verify against --help --> |
| RM-6 | Temporal generalization gap | `test_random` F1 − `test_time` F1 | reported, not gamed | `research/experiments/e6_*` <!-- verify against --help --> |

All RM values are `<!-- TODO(measure): fill after E1–E6 -->`.

### 7.2 Engineering metrics

| ID | Metric | Target | Produced by |
|---|---|---|---|
| EM-1 | `/analyze` p95 latency (stub) | ≤ 150 ms | load test over `services/api`, <!-- TODO(measure): record harness --> |
| EM-2 | `/analyze` p95 latency (transformer, CPU) | ≤ 2 s (provisional) | `research/experiments/e7_*` <!-- verify against --help --> |
| EM-3 | Cold start (stub / full) | ≤ 1 s / ≤ 60 s | startup timing in CI logs |
| EM-4 | Eval-regression gate | CI fails if a locked-split metric drops beyond tolerance | `.github/workflows/` eval gate |
| EM-5 | Test suite | green on `main`; architecture test enforced | `pytest tests/ -q` |

### 7.3 Product metrics

| ID | Metric | Target | Produced by |
|---|---|---|---|
| PM-1 | End-to-end usable app | A reader can go source text → prediction → evidence → timeline without leaving the app | manual walkthrough |
| PM-2 | Evidence coverage | 100% of displayed predictions show ≥1 evidence span or an explicit limitation | UI test `<!-- TODO(measure) -->` |
| PM-3 | Abstention correctness | Copilot abstains when supporting evidence is absent | copilot eval set <!-- TODO(measure) --> |

## 8. Acceptance criteria (definition of done)

### Release 1 — Core
- Corpus ingest + dedupe + provenance complete for ≥1 tier-1 source and ≥1
  official source, with manifests committed.
- Annotation schema, guide, and a first labelled set with agreement scores.
- Document sentiment and NER models trained on locked splits, with baselines.
- `POST /analyze`, `GET /health`, `GET /models` live; stub fallback works
  offline.
- `docs/` SRS, data card, model card, reproduce, limitations present.
- Test suite green incl. architecture test.

### Release 2 — Intelligence
- Event classification, entity-level sentiment, and entity resolution shipped.
- Event dedup, timelines, novelty, narrative shifts.
- Frontend views for news, entities, events, playground; evidence and
  limitations visible.
- Copilot with citations and abstention.
- E1–E6 reported with variance and CIs on all three splits.

### Release 3 — Research platform
- NaijaFin-Bench published with leaderboard and reproduction guide.
- E7–E9 (efficiency, error analysis, ablations) complete.
- Eval-regression gate wired into CI.
- Public data/URLs/labels release under the licence policy.

## 9. Constraints and assumptions

**Constraints**
- Article bodies are copyrighted; redistribution is restricted per source.
- Annotation is human-bounded; only 15–20% can be double-annotated.
- Local compute: CPU-first, single machine; GPU optional.
- No reliance on paid APIs for the core path.

**Assumptions**
- Sources remain accessible under their audited terms; ToS/robots may change.
- `constants.py` remains the single source of truth for label spaces (guarded
  by asserts in `schemas.py`).
- The inference path stays framework-free and swappable behind
  `AnalysisPipeline`.

## 10. Dependencies

- **Runtime:** Python ≥3.11, `pydantic>=2.7`, `pydantic-settings`, `httpx`,
  `tenacity`, `beautifulsoup4`, `lxml`, `trafilatura`, `numpy`, `pandas`,
  `scipy`, `scikit-learn`, `joblib`, `datasketch`, `rapidfuzz`.
- **API extra:** `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg`,
  `python-multipart`, `aiosqlite`.
- **ML extra:** `transformers`, `tokenizers`, `seqeval`, `spacy`,
  `python-crfsuite`.
- **LLM extra:** `anthropic` (optional).
- **Efficiency extra:** `onnxruntime` (optional).
- **Dev extra:** `pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`,
  `pre-commit`.

## 11. Risks and mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Source access changes / ToS blocks scraping | Corpus stalls | Medium | Multi-source manifest; HTML/RSS/sitemap fallbacks; official releases are likely stable; honour robots and rate limits |
| Copyright limits redistribution | Can't ship raw text | High | Publish labels + URLs + rebuild scripts; per-source `license_note`; official releases tracked separately |
| Annotation bottleneck | Small labelled N | High | LLM pre-label + mandatory human review; active selection; report agreement; never treat pre-labels as gold |
| Small data → unstable metrics | Misleading results | High | ≥3 seeds, variance + CIs; report slices; avoid single-number claims |
| Leakage (dupes/syndication/temporal) | Inflated scores | Medium | `content_hash` + MinHash dedup; duplicates in exactly one split; time-held-out split |
| Financial misuse (read as advice) | Harm/reputational | Medium | Disclaimers in API + UI; non-goals; no forecasts; no trading signals |
| Hosting limits (CPU, memory) | Slow service | Medium | Stub fallback; ONNX/quantised path; payload caps; batch caps |
| LLM pre-labelling bias | Circular labels | Medium | Disclosure via `model_prelabel`; human review mandatory; measure LLM-only vs human-only agreement |

## 12. Traceability

| Requirement family | Code path | Document / card |
|---|---|---|
| FR-CORPUS-1..8 | `naijafinsent/data`, `data/manifests/`, `naijafinsent/config.py` | `docs/SOURCES.md`, `docs/DATA_CARD.md`, `data/README.md` |
| FR-CORPUS-9..12 | `naijafinsent/deduplication`, `naijafinsent/data` | `docs/DATA_CARD.md`, `docs/LIMITATIONS.md` |
| FR-ANNOT-1..6 | `naijafinsent/annotation`, `data/annotation`, `naijafinsent/schemas.py` | `docs/ANNOTATION_GUIDE.md`, `docs/DATA_CARD.md` |
| FR-MODEL-1..7 | `naijafinsent/{sentiment,ner,event_extraction,entity_resolution}`, `naijafinsent/inference/pipeline.py` | `docs/MODEL_CARD.md` |
| FR-EVENT-1..6 | `naijafinsent/event_extraction`, `naijafinsent/deduplication` | `docs/MODEL_CARD.md`, `docs/CASE_STUDY.md` |
| FR-EVENT-7..9 | `naijafinsent/entity_resolution` | `docs/MODEL_CARD.md`, `docs/LIMITATIONS.md` |
| FR-API-1..9 | `services/api/app`, `naijafinsent/schemas.py` | `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` |
| FR-UI-1..5 | `apps/web` | `docs/DEPLOYMENT.md` |
| FR-BENCH-1..6 | `naijafinsent/baselines`, `naijafinsent/evaluation`, `research/` | `docs/EVALUATION.md`, `docs/DATA_CARD.md`, `docs/MODEL_CARD.md` |
| FR-COPILOT-1..4 | `services/api/app`, `apps/web` | `docs/MODEL_CARD.md`, `docs/LIMITATIONS.md` |
| NFR-1..9 | whole repo; `naijafinsent/config.py`; `tests/test_architecture.py` | all docs; `CONTRIBUTING.md` |
| RM-1..6 | `naijafinsent/evaluation`, `research/experiments/` | `docs/EVALUATION.md`, `docs/MODEL_CARD.md` |
| EM-1..5 | `services/api`, `.github/workflows/`, `tests/` | `docs/DEPLOYMENT.md`, `docs/REPRODUCE.md` |
| PM-1..3 | `apps/web`, copilot eval set | `docs/CASE_STUDY.md` |
