# Deployment

## Docker compose (full stack)

```bash
cd infra
docker compose up --build
```

| Service | Image | Port | Notes |
|---|---|---|---|
| `db` | `postgres:16-alpine` | — | healthcheck `pg_isready`; volume `pgdata` |
| `api` | `infra/api.Dockerfile` | 8000 | `uvicorn app.main:app`, healthcheck on `/api/v1/health` |
| `worker` | `infra/worker.Dockerfile` | — | `python -m app.worker --once --limit 100` per cycle |
| `web` | `infra/web.Dockerfile` | 3000 | builds `apps/web`, serves the static bundle |

The API and worker connect via `DATABASE_URL=postgresql+psycopg://...`; the web
bundle points at the API with `VITE_API_BASE_URL`.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | api, worker, tests | `sqlite:///...` for dev/CI, postgres otherwise |
| `NAIJAFINSENT_DATA_DIR` | api, worker | corpus + manifest root |
| `CORS_ORIGINS` | api | browser origins allowed to call the API |
| `VITE_API_BASE_URL` | web | base URL for the typed client (default `http://localhost:8000`) |
| `VITE_USE_MOCKS` | web | `true` serves synthetic fixtures through the same client |

## Running without Docker

```bash
# API
cd services/api
uvicorn app.main:app --host 0.0.0.0 --port 8000        # PYTHONPATH already satisfied by cwd

# Worker (one-shot per cron tick, or a slow loop)
python -m app.worker --once --limit 100
python -m app.worker --loop 900 --limit 100

# Web
cd apps/web && npm install && npm run dev              # http://localhost:5173
```

## CI (`.github/workflows/ci.yml`)

Single workflow, two jobs:

1. **lint-and-test** — install `.[dev,api]`, ruff (best-effort), the
   architecture guard (`tests/test_architecture.py`, core stays
   framework-free), the full pytest suite, and `scripts/smoke_api.py` against a
   throwaway SQLite database.
2. **eval-regression-gate** — `scripts/eval_gate.py --tolerance 0.02` on a
   locked golden set vs `research/baselines/golden_baseline.json`. A quality
   drop blocks the merge; refreshing a baseline is an explicit commit.

## Operational notes

- `/api/v1/health` (liveness) and `/api/v1/health/ready` (readiness) are the
  probe endpoints for any orchestrator.
- The worker treats every source independently: one failing source increments
  `errors` in the cycle summary but never aborts the cycle.
- Migrations: Alembic is installed with the `api` extra; SQLite (dev) creates
  via metadata on first use, Postgres deployments should run `alembic upgrade
  head` before the first API start.
- Everything the API returns carries the disclaimer chain: "measurements of
  language in published coverage — not investment advice, no causal claims."
