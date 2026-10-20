# Sun/monorepo layout

/naijafinsent/  -> core package (framework-free, architecture-tested)
/services/api/  -> FastAPI service (depends on core, never the reverse)
/services/worker-> scheduled ingestion + batch inference
/apps/web/      -> React + TS + Vite + Tailwind + TanStack Query
/research/      -> notebooks, experiment runners, reports
/data/          -> manifests, fixtures, annotation exports, trained models
/docs/          -> SRS, architecture, annotation guide, data/model cards, evaluation
/infra/         -> Docker, deployment
/tests/         -> cross-package tests incl. architecture test
