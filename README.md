# NaijaFinSent

**One line:** a Nigeria-focused financial NLP and event-intelligence platform. It reads Nigerian financial news, extracts entities, sentiment, and structured events with evidence, and publishes an open benchmark that tests whether local, entity-aware models beat generic finance models.

**Research question:** how much do Nigeria-specific language and entity-aware modelling improve sentiment, NER, and event extraction over general-purpose models, LLMs, and finance-domain baselines?

> ⚠️ **Not investment advice.** NaijaFinSent measures language in published news coverage. It makes no causal or predictive claim about prices or returns. Every prediction in the app links back to the source text and its evidence span.

---

## What is in this repo

| Layer | Path | What it does |
|---|---|---|
| Corpus | `naijafinsent/data` | Provenance-tracked Nigerian financial news and official releases |
| Annotation | `naijafinsent/annotation`, `data/annotation` | Guide, tooling, agreement scores, locked splits |
| Models | `naijafinsent/{sentiment,ner,event_extraction,entity_resolution}` | Sentiment, NER, entity-level sentiment, event extraction, entity resolution |
| Baselines | `naijafinsent/baselines` | TF-IDF, CRF, FinBERT zero-shot, few-shot LLM |
| Intelligence | `naijafinsent/{deduplication,event_extraction}` | Event dedup, timelines, novelty, narrative shifts |
| Benchmark | `data/annotation`, `docs/EVALUATION.md` | NaijaFin-Bench: data, baselines, leaderboard |
| API | `services/api` | FastAPI + Pydantic, Postgres/SQLite, migrations |
| Worker | `services/worker` | Scheduled ingestion + batch inference |
| App | `apps/web` | React dashboard: news, entities, events, model lab, playground |
| Core | `naijafinsent/` | Framework-free package, enforced by an architecture test |

## Quickstart (local, zero external models)

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows
pip install -e ".[dev,api]"
cp .env.example .env
python -m naijafinsent.cli demo   # runs the deterministic stub pipeline offline
uvicorn services.api.app.main:app --reload
```

The API and app run without any trained models: they fall back to the
deterministic, rule-based stub pipeline so every endpoint is testable offline.

## Reproducing the benchmark

```bash
python -m naijafinsent.cli ingest --source businessday --limit 20   # respect ToS
python -m naijafinsent.cli dedupe
python -m naijafinsent.cli splits build
python -m naijafinsent.cli eval run --split test_random
python -m naijafinsent.cli eval report --out research/reports
```

See `docs/REPRODUCE.md` for the full pipeline, seeds, and hardware notes.

## Documentation

- [SRS](docs/SRS.md) — scope, users, success metrics, non-goals
- [Architecture](docs/ARCHITECTURE.md) — components, data flow, provenance
- [Annotation guide](docs/ANNOTATION_GUIDE.md) — label policy and edge cases
- [Data card](docs/DATA_CARD.md) — provenance, licensing, splits, known biases
- [Model card](docs/MODEL_CARD.md) — intended use, metrics, limitations
- [Evaluation](docs/EVALUATION.md) — E1–E9 experiments, results, error analysis
- [Deployment](docs/DEPLOYMENT.md) — Docker, hosting, CI, the eval regression gate
- [Sources](docs/SOURCES.md) — Stage 0 source audit and access policy

## Licence and data policy

Code is MIT. **We publish labels, URLs, and rebuild scripts — not full article
text.** See [docs/SOURCES.md](docs/SOURCES.md) for the per-source access policy
and the data card for what is redistributable.
