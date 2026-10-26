# Repo map (accurate layout)

| Path | Role |
|---|---|
| `naijafinsent/` | core package (framework-free, enforced by `tests/test_architecture.py`) |
| `services/api/` | FastAPI service — run `uvicorn app.main:app` **from this directory** (or set `PYTHONPATH=services/api`) |
| `services/api/app/worker.py` | scheduled ingestion + analysis loop: `python -m app.worker --once` / `--loop` |
| `apps/web/` | React + TS + Vite + Tailwind + TanStack Query console |
| `research/` | committed baselines (`research/baselines/`), reports, experiment runners |
| `data/` | manifests, fixtures, annotation exports, trained models (see `data/README.md`) |
| `docs/` | SRS, architecture, annotation guide, data/model cards, evaluation, deployment |
| `infra/` | Dockerfiles + `docker-compose.yml` (api, worker, web, postgres) |
| `tests/` | cross-package tests, including the architecture and locked-split guards |
| `scripts/` | `smoke_api.py`, `eval_gate.py` (CI gate), import rewriter, helpers |

## Environment notes (Windows dev)

- Tests/API expect `DATABASE_URL` (e.g. `sqlite:///./.test_db/test.db`) and
  `PYTHONPATH=services/api` when pytest runs from the repo root.
- The naira sign (`₦`) requires `PYTHONIOENCODING=utf-8` in some consoles.
