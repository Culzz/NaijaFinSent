# Architecture

## The one rule: core stays framework-free

`naijafinsent/` (the core package) imports no FastAPI, no SQLAlchemy, no service
code. The API may import the core package — never the reverse. This is enforced
by a test: run `pytest tests/test_architecture.py`.

```
┌──────────────────────────────────────────────────────────────────┐
│ deps: FastAPI, SQLAlchemy, Alembic, scikit-learn (opt), LLM (opt)│
├──────────────────────────────────────────────────────────────────┤
│ services/api        FastAPI app (app.main:app), run with         │
│                     cwd/PYTHONPATH = services/api                │
│ services/api/app/worker.py   ingest + analysis loop              │
├──────────────────────────────────────────────────────────────────┤
│ naijafinsent/       core package: data, annotation, sentiment,    │
│                     ner, event_extraction, entity_resolution,    │
│                     evaluation, inference, bench                 │
│                     (framework-free — no web/db imports)         │
└──────────────────────────────────────────────────────────────────┘
```

## Layout

| Path | Role |
|---|---|
| `naijafinsent/data/` | provenance-tracked ingest, article dedup, corpus store |
| `naijafinsent/annotation/` | label schema, IOB tagmaps, agreement scoring, locked splits |
| `naijafinsent/sentiment/` | TF-IDF/transformer/lexicon models + calibration |
| `naijafinsent/ner/` | rule-based NER and trained models |
| `naijafinsent/event_extraction/` | keyword triggers, TF-IDF classifier, attributes, event clustering |
| `naijafinsent/entity_resolution/` | staged resolver (alias → fuzzy → context) |
| `naijafinsent/evaluation/` | metrics with CIs, slices, bootstrap |
| `naijafinsent/inference/` | `AnalysisPipeline` + `StubPipeline` (deterministic, weights-free) |
| `services/api/` | FastAPI service: `uvicorn app.main:app` (run from `services/api`) |
| `services/api/app/worker.py` | `python -m app.worker --once` or `--loop` |
| `apps/web/` | React console (Vite, TanStack Query) |
| `infra/` | Dockerfiles + `docker-compose.yml` |

## The offline demo path

`StubPipeline` wires **deterministic models only** — `LexiconSentimentModel`,
`RuleBasedNer`, `KeywordEventModel`, `EntityResolver` — so the API, worker,
frontend, and CI run with **zero trained weights** on any machine. Every
prediction carries exact evidence spans and the pipeline's limitation notes,
including "not investment advice".

## Two clocks, never merged

Across the corpus, events, API, and every UI timeline, three dates are stored
separately: **event date** (when it happened), **publish date** (first report
seen), and **processing date** (when we ingested it). Report-level dedup keys on
content; event-level clustering keys on type + entities + date proximity + text
similarity with documented weights (see `naijafinsent/event_extraction/dedup.py`).

## Data flow

1. `Fetcher` → audited sources only (manifest + robots check, SSRF guard).
2. `Ingestor` extracts text (`trafilatura`, lazily imported), computes
   `content_hash`, MinHash signatures, and clustered duplicates.
3. Analysis pipeline attaches sentiment, entities, entity-level sentiment, and
   events with evidence to each non-duplicate article.
4. `EventClusterer` collapses multi-article coverage into clusters, computes
   `whats_new` novelty, coverage intensity, and sentiment-shift signals — all
   framed as *coverage language*, never market causation.
5. The API exposes everything above with repository-backed endpoints; the worker
   automates steps 1–4 on a schedule.
