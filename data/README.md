# `data/` — layout, what is committed, what is not

This directory holds corpus metadata, test fixtures, annotation exports, and
trained models. Because the platform ingests **copyrighted third-party
journalism**, the commit policy here is deliberately strict.

> Legal policy reminder: we publish **labels, URLs, and rebuild scripts — not
> full article text**, except where a source's `license_note` explicitly
> permits it. See `docs/SOURCES.md` and `docs/DATA_CARD.md` §7.

---

## Layout

```
data/
├── manifests/    # source audit + manifest entries (COMMITTED)
├── fixtures/     # small, non-substitutable test fixtures (COMMITTED)
├── annotation/   # schema export, lexicon, split manifests (COMMITTED)
├── corpus/       # fetched article bodies (GITIGNORED)
├── raw/          # raw HTTP responses / HTML (GITIGNORED)
├── processed/    # normalised/derived text (GITIGNORED)
└── models/       # trained weights + registry (GITIGNORED)
```

## Committed

| Path | Contents | Why it is safe to commit |
|---|---|---|
| `data/manifests/` | `SourceManifestEntry` records: `source_id`, `base_url`, `url_pattern`, `access_method`, `license_note`, `trust_tier`, `robots_checked_at`, `enabled`, `notes` | Metadata and access policy, not content |
| `data/fixtures/` | Small hand-made test fixtures (short snippets, synthetic examples) | Bounded, non-substitutable, needed for tests |
| `data/annotation/` (schema + lexicon) | Annotation JSON schema / label config, entity alias lexicon | Our own definitions, not source text |
| `data/annotation/` (splits manifests) | Split definitions and hashes: `train`, `dev`, `test_random`, `test_source`, `test_time` | Pointers and hashes; enables reproducibility |
| `data/annotation/` (labels) | Annotation labels (our contribution) | We own the labels; released for research use |

Labels reference `article_id` and `text` spans; article bodies stay out of git.

## Gitignored (see `.gitignore`)

| Path | Contents | Why ignored |
|---|---|---|
| `data/corpus/` | Fetched article bodies | Copyright; rebuildable via `cli ingest` |
| `data/raw/` | Raw responses/HTML | Copyright + size; rebuildable |
| `data/processed/` | Normalised/derived text | Derivative of copyrighted text |
| `data/models/` | Trained weights, `registry.json` | Large binaries; `*.pt/*.bin/*.safetensors/*.joblib/*.onnx` are ignored |

Also ignored repo-wide: `.env`, `*.pem`, notebooks checkpoints, and any
`wandb/`/`runs/` artifacts.

## Repository registry

The model registry lives at `data/models/registry.json`
(`NFS_MODEL_REGISTRY_PATH`) and is **gitignored**. Published model metadata
(name, version, task, metrics) is documented in `docs/MODEL_CARD.md`; the
registry file is a runtime artifact, not a source of truth.

## Rebuilding the ignored data

```bash
python -m naijafinsent.cli ingest --source businessday --limit 20   # respect ToS
python -m naijafinsent.cli dedupe
python -m naijafinsent.cli splits build
```

Ingestion requires network access and honours each source's `access_method`,
rate limits, robots policy, and `license_note`. To reproduce results offline,
use the committed fixtures and label sets under `data/fixtures/` and
`data/annotation/`.

## Rules

1. **Never commit article body text** for sources whose `license_note` does not
   permit it. Short evidence spans in fixtures are the only exception.
2. **Never commit trained models or weights** — they are rebuildable.
3. **Never commit secrets** (`.env`, keys, tokens).
4. **Respect source terms.** Disable a source (`enabled=false`) when its terms
   change, and record why in `notes`.
5. **Keep provenance.** New data must be traceable to a manifest entry.
