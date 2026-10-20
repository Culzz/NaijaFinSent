# Reproducing NaijaFinSent

This is a copy-pasteable guide to rebuild the corpus, run the baselines, train
the models, evaluate, and run the app locally. Commands reference the real
module paths; where an exact flag is not yet fixed it is marked
`<!-- verify against --help -->`.

> Reminder: **not investment advice.** Reproducing this pipeline reproduces a
> language-analysis benchmark, not a trading system.

---

## 1. System requirements

- **OS:** Windows, macOS, or Linux.
- **Python:** ≥ 3.11 (see `pyproject.toml` `requires-python`).
- **RAM:** 8 GB minimum; 16 GB recommended for transformer training.
- **Disk:** ≥ 2 GB for corpus + models (transformer weights are large).
- **GPU:** optional. Everything is CPU-runnable; GPU speeds training.
- **Network:** required only for ingestion and LLM steps; the stub pipeline and
  most tests run fully offline.

## 2. Environment setup

```bash
git clone https://github.com/Culzz/NaijaFinSent
cd NaijaFinSent
python -m venv .venv
```

Activate:

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

## 3. Dependency tiers

`pyproject.toml` defines extras. Install the tiers you need:

```bash
pip install -e .                 # base: pydantic, httpx, trafilatura, sklearn, datasketch, rapidfuzz...
pip install -e ".[api]"          # FastAPI, uvicorn, SQLAlchemy, Alembic, psycopg, aiosqlite
pip install -e ".[ml]"           # transformers, tokenizers, seqeval, spacy, python-crfsuite
pip install -e ".[llm]"          # anthropic (few-shot LLM baseline / copilot prose)
pip install -e ".[efficiency]"   # onnxruntime (quantised/ONNX serving path)
pip install -e ".[dev]"          # pytest, pytest-cov, pytest-asyncio, ruff, pre-commit
```

Typical combos:

```bash
pip install -e ".[dev,api]"          # offline dev + API (README quickstart)
pip install -e ".[dev,api,ml,llm]"   # full benchmark reproduction
```

## 4. Environment variables

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Key variables (see `.env.example` and `naijafinsent/config.py`):

| Variable | Purpose | Default |
|---|---|---|
| `NFS_ENV` | Environment name | `development` |
| `NFS_LOG_LEVEL` | Log level | `INFO` |
| `NFS_DATABASE_URL` | DB (SQLite local, Postgres prod) | `sqlite:///./data/naijafinsent.db` |
| `NFS_API_HOST` / `NFS_API_PORT` | API bind | `127.0.0.1` / `8000` |
| `NFS_CORS_ORIGINS` | Allowed origins | `http://localhost:5173` |
| `NFS_RATE_LIMIT_PER_MINUTE` | API rate limit | `60` |
| `NFS_MAX_TEXT_CHARS` | Max text length | `20000` |
| `NFS_MAX_BATCH_SIZE` | Max batch size | `32` |
| `NFS_USER_AGENT` | Bot identity for fetches | research bot UA |
| `NFS_FETCH_RATE_LIMIT_SECONDS` | Polite fetch delay | `2.0` |
| `NFS_FETCH_MAX_BYTES` / `_TIMEOUT_SECONDS` / `_MAX_REDIRECTS` | Fetch guards | `2000000` / `20.0` / `5` |
| `NFS_INGEST_CRON` | Scheduled ingest | `0 */6 * * *` |
| `NFS_MODEL_REGISTRY_PATH` | Model registry | `data/models/registry.json` |
| `ANTHROPIC_API_KEY` | LLM baseline / copilot (optional) | empty |
| `WANDB_PROJECT` | Experiment tracking (optional) | empty |

**Never commit `.env` or real keys.**

## 5. Hardware and runtime expectations

| Step | Hardware | Expected wall-clock |
|---|---|---|
| Stub demo + API | any CPU | seconds |
| Ingest N sources | any CPU, network | minutes (rate-limited) |
| Dedupe + splits | any CPU | seconds–minutes |
| TF-IDF baselines | any CPU | minutes |
| Transformer fine-tuning | 1 GPU recommended | `<!-- TODO(measure): record on reference hardware -->` |
| Full benchmark (E1–E9) | 1 GPU | `<!-- TODO(measure): record end-to-end runtime -->` |

Record your own times; this table is a placeholder until measured.

## 6. Full pipeline sequence

Run in order. Nothing here requires a GPU until training.

```bash
# 0. sanity: deterministic offline stub pipeline
python -m naijafinsent.cli demo

# 1. ingest (respect ToS; source must be in the manifest)
python -m naijafinsent.cli ingest --source businessday --limit 20

# 2. deduplicate (exact + MinHash + syndication)
python -m naijafinsent.cli dedupe

# 3. build locked splits (random / source-held-out / time-held-out)
python -m naijafinsent.cli splits build

# 4. baselines (TF-IDF + LR/SVM, etc.)
python -m naijafinsent.baselines.run

# 5. train models
python -m naijafinsent.cli train --task sentiment   <!-- verify against --help -->
python -m naijafinsent.cli train --task ner         <!-- verify against --help -->
python -m naijafinsent.cli train --task events      <!-- verify against --help -->

# 6. evaluate on a locked split
python -m naijafinsent.cli eval run --split test_random

# 7. report
python -m naijafinsent.cli eval report --out research/reports
```

The README quickstart shows steps 1–7 condensed; the full order above is the
canonical sequence.

## 7. Seeds and variance

- All stochastic steps take a seed; experiments run over **≥3 seeds**.
- Report **variance and confidence intervals**, never a single point estimate.
- The number and values of seeds are fixed in the experiment runner. To
  reproduce exactly, use the same seed set the reports were generated with.

`<!-- verify against --help: confirm the exact --seed / --seeds flag names on
cli train, baselines.run, and evaluation.runner -->`

## 8. Reproducing each experiment (E1–E9)

Each experiment is a standalone script under `research/experiments/`.

```bash
python research/experiments/e1_local_vs_generic.py
python research/experiments/e2_entity_vs_document.py
python research/experiments/e3_*      # NER-focused    <!-- verify against --help -->
python research/experiments/e4_*      # entity resolution <!-- verify against --help -->
python research/experiments/e5_*      # source-held-out generalization <!-- verify against --help -->
python research/experiments/e6_*      # time-held-out generalization <!-- verify against --help -->
python research/experiments/e7_*      # efficiency / latency / calibration <!-- verify against --help -->
python research/experiments/e8_*      # error analysis <!-- verify against --help -->
python research/experiments/e9_*      # ablations <!-- verify against --help -->
```

Intent by experiment (definitive list in `docs/EVALUATION.md`):

| ID | Intent |
|---|---|
| E1 | Local models vs generic/finance-domain/LLM baselines |
| E2 | Entity-aware vs document-only (the delta) |
| E3 | NER across model families and slices |
| E4 | Entity resolution accuracy and ambiguous handling |
| E5 | Publisher generalization (source-held-out) |
| E6 | Temporal generalization (time-held-out) |
| E7 | Efficiency: latency, memory, calibration (ECE) |
| E8 | Error analysis: recurring failure modes |
| E9 | Ablations: features, preprocessing, label policy |

## 9. Running the API locally

```bash
uvicorn services.api.app.main:app --reload
```

- `POST /analyze` — full `AnalysisResult` for one text.
- Batch endpoint — capped at `NFS_MAX_BATCH_SIZE`.
- `GET /health`, `GET /models` — introspection.
- Read endpoints — articles, entities, events, timelines, trends.

OpenAPI docs at `http://127.0.0.1:8000/docs`.

**No trained model is required.** Without one, the API uses
`StubPipeline`, which is deterministic and offline.

## 10. Running the frontend locally

```bash
cd apps/web
npm install
npm run dev
```

The dev server binds to `http://localhost:5173` (matches the default
`NFS_CORS_ORIGINS`). Point it at the API via the configured base URL.
`<!-- verify: confirm the Vite env var name for the API base URL -->`

## 11. Test suite and CI eval-regression gate

```bash
# full suite
pytest tests/ -q

# skip slow / network tests
pytest tests/ -q -m "not slow and not network"

# architecture rule (framework-free core)
pytest tests/test_architecture.py -q
```

Markers (`pyproject.toml`): `slow` and `network` (network tests are deselected
by default in CI).

The **eval-regression gate** re-runs locked-split evaluation in CI and fails
the build if a metric drops beyond tolerance. Run it locally as:

```bash
python -m naijafinsent.cli eval run --split test_random --gate   <!-- verify against --help -->
```

## 12. Network, LLM keys, and graceful degradation

| Step | Needs network? | Needs LLM key? | If unavailable |
|---|---|---|---|
| `cli demo`, stub API, most tests | No | No | Works as-is |
| `cli ingest` | Yes | No | Fails fast with a clear fetch error; use committed fixtures/`research/reports` instead |
| Baselines (TF-IDF) | No | No | Works on committed labels |
| Few-shot LLM baseline | Yes | Yes (`ANTHROPIC_API_KEY`) | Skipped; report it as "not run", never as zero |
| Transformer training | No (after weights cached) | No | First run downloads weights; offline needs a local cache |
| Copilot prose | Yes | Yes | Degrades to retrieval-with-citations, no generated prose |

Never report a skipped LLM baseline as a score. Report it as
**not run** with the reason.

## 13. Troubleshooting

- **`ModuleNotFoundError` for an extra:** install the matching tier (§3).
- **Ingest empty:** the source may be `enabled=false` or robots/ToS changed —
  check `data/manifests/`.
- **Split leakage check fails:** duplicates/syndicated copies must be in one
  split; rebuild splits and re-run the leakage test.
- **Slow API:** you are loading transformers; use stub mode or the ONNX
  (`efficiency`) path.
- **Numbers differ between runs:** expected. Report seed variance and CIs
  (§7).
