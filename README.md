# NaijaFinSent

**One line:** a Nigeria-focused financial NLP and event-intelligence platform. It reads Nigerian financial news, extracts entities, sentiment, and structured events with evidence, and publishes an open benchmark that tests whether local, entity-aware models beat generic finance models.

**Research question:** how much do Nigeria-specific language and entity-aware modelling improve sentiment, NER, and event extraction over general-purpose models, LLMs, and finance-domain baselines?

> ⚠️ **Not investment advice.** NaijaFinSent measures language in published news coverage. It makes no causal or predictive claim about prices or returns. Every prediction in the app links back to the source text and its evidence span.

**Status:** the platform is complete and CI-gated — 374 tests pass, the frontend builds, the API + worker + docker-compose stack run end to end, and an eval regression gate blocks silent quality drops.

---

## What is in this repo

| Layer | Path | What it does |
|---|---|---|
| Core | `naijafinsent/` | Framework-free package (architecture test enforces it) |
| Corpus | `naijafinsent/data/` | Provenance-tracked Nigerian financial news and official releases |
| Annotation | `naijafinsent/annotation/` | Guide tooling, agreement scores, locked splits |
| Models | `naijafinsent/{sentiment,ner,event_extraction,entity_resolution}/` | Sentiment, NER, entity-level sentiment, event extraction, entity resolution |
| Intelligence | `naijafinsent/event_extraction/dedup.py` | Event-level clustering, timelines, novelty, narrative shifts |
| Benchmark | `naijafinsent/bench.py`, `data/annotation/` | NaijaFin-Bench: three views, rebuild manifest, policy guard |
| API | `services/api/` | FastAPI + Pydantic + SQLAlchemy (SQLite dev / Postgres prod) |
| Worker | `services/api/app/worker.py` | Scheduled ingestion + analysis (per-source isolated) |
| App | `apps/web/` | React console: news, entities, events, narratives, model lab, playground |
| Eval gate | `scripts/eval_gate.py` | Golden-set regression gate with a frozen baseline |
| Infra | `infra/` | Dockerfiles + `docker-compose.yml` (api, worker, web, postgres) |

## Quickstart (local, zero external models)

```bash
python -m venv .venv
# Windows: . .venv/Scripts/activate    |  Linux/macOS: . .venv/bin/activate
pip install -e ".[dev,api]"

# Run the deterministic pipeline offline
python -m naijafinsent.cli demo
```

### API

```bash
cd services/api
uvicorn app.main:app --reload          # http://localhost:8000
```

The API runs **without any trained models**: the `StubPipeline` wires the
deterministic lexicon/rule models, so every route (`/api/v1/inference/analyze`,
events, entities, watchlists, notifications, …) is testable offline and every
prediction carries evidence spans and the limitation notes. Interactive docs:
`http://localhost:8000/docs`.

### Worker

```bash
cd services/api
python -m app.worker --once --limit 100    # single ingest+analyze cycle
python -m app.worker --loop 900            # or a 15-minute loop
```

One failing source never aborts a cycle — errors are counted per source.

### Web console

```bash
cd apps/web
npm install
npm run dev                        # http://localhost:5173
```

Point it at the API with `VITE_API_BASE_URL` (default `http://localhost:8000`).
To review the UI without a backend, `VITE_USE_MOCKS=true` serves clearly-labelled
synthetic fixtures through the same client.

### Full stack with Docker

```bash
cd infra
docker compose up --build          # api :8000, web :3000, postgres, worker
```

## Development

```bash
# Tests (374 passing; use the same env the CI job uses)
set DATABASE_URL=sqlite:///./.test_db/test.db     # PowerShell: $env:...
pytest tests -q

# Architecture guard — the core package stays framework-free
pytest tests/test_architecture.py

# API smoke (throwaway SQLite, all routes)
python scripts/smoke_api.py

# Frontend build (tsc strict + vite bundle)
cd apps/web && npm run build
```

The Prometheus-style golden rule of this repo: **a merged change is (a) green on
CI, (b) evidence-preserving, (c) still honest about what the model does not
know.**

## Reproducing the benchmark

```bash
python -m naijafinsent.cli ingest --source businessday --limit 20   # respect ToS
python -m naijafinsent.cli dedupe
python -m naijafinsent.cli splits build
python -m naijafinsent.cli eval run --split test_random
python -m naijafinsent.cli eval report --out research/reports
```

The locked test split is never tuned on (guarded by `tests/test_locked_guard.py`);
model selection happens on dev. Results report seeds and bootstrap CIs. See
`docs/REPRODUCE.md` for the full pipeline and `docs/EVALUATION.md` for the
metric discipline and the regression-gate policy.

## CI

`.github/workflows/ci.yml` runs two jobs on every push/PR:

1. **lint-and-test** — ruff, the architecture guard, the full pytest suite, and
   the API smoke against a throwaway database;
2. **eval-regression-gate** — `scripts/eval_gate.py` re-runs the committed
   golden set (baseline: `research/baselines/golden_baseline.json`, accuracy
   0.6667, tolerance 0.02). A drop in gated quality fails the job.

## Documentation

- [SRS](docs/SRS.md) — scope, users, success metrics, non-goals
- [Architecture](docs/ARCHITECTURE.md) — layers, data flow, the two-clock rule
- [Annotation guide](docs/ANNOTATION_GUIDE.md) — label policy and edge cases
- [Data card](docs/DATA_CARD.md) — provenance, licensing, splits, known biases
- [Model card](docs/MODEL_CARD.md) — intended use, metrics, limitations
- [Evaluation](docs/EVALUATION.md) — metrics, CIs, slices, the E1–E9 map, the gate
- [Deployment](docs/DEPLOYMENT.md) — Docker, env vars, CI, operational notes
- [Limitations](docs/LIMITATIONS.md) — what this system does not claim
- [Sources](docs/SOURCES.md) — Stage 0 source audit and access policy

## Licence and data policy

Code is MIT. **We publish labels, URLs, and rebuild scripts — not full article
text.** See [docs/SOURCES.md](docs/SOURCES.md) for the per-source access policy
and the data card for what is redistributable.
