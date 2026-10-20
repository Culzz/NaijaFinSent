# Contributing to NaijaFinSent

Thanks for helping build an auditable, Nigeria-focused financial NLP platform.
This document covers dev setup, code style, the architectural rules, how to
extend the label spaces, testing, PR conventions, and the data-handling rules
that keep us legally safe.

> Not investment advice. Contributions must not introduce advisory, trading,
> or predictive functionality — see the non-goals in `docs/SRS.md` §3.1.

---

## 1. Development setup

```bash
git clone https://github.com/Culzz/NaijaFinSent
cd NaijaFinSent
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on *nix)
pip install -e ".[dev,api]"
pre-commit install
cp .env.example .env          # Windows: copy .env.example .env
pytest tests/ -q
```

Add `ml`, `llm`, or `efficiency` extras only if your work needs them.

## 2. Code style

- **Linter/formatter:** `ruff`. Config in `pyproject.toml`.
- **Line length:** 100.
- **Lint rules:** `E, F, I, UP, B, C4` (with `E501` ignored because ruff-format
  handles wrapping).
- **Target:** Python 3.11 (`target-version = "py311"`).
- Russian-doll it: keep imports sorted (ruff `I`), prefer modern syntax
  (ruff `UP`).

```bash
ruff check . --fix
ruff format .
```

## 3. The framework-free-core rule

`naijafinsent/` is the **core package** and must stay framework-free and
dependency-light. It must **not** import FastAPI, SQLAlchemy, transformers,
torch, or any serving/web/DB framework — those belong in `services/api`,
`services/worker`, or optional extras.

The API depends on the core; the core never depends on the API. This keeps the
core testable, portable, and the serving stack swappable behind
`AnalysisPipeline`.

**This rule is enforced by an architecture test:**

```bash
pytest tests/test_architecture.py -q
```

Any PR that violates it fails CI. If you need a dependency in the core, argue
for it in the PR and update the test only if the rule itself is changing.

## 4. Never tune on the locked test set

- Locked test splits are `test_random`, `test_source`, `test_time`.
- Their labels are frozen and hash-pinned.
- **Never** train, hyper-parameter tune, feature-select, calibrate, or eyeball
  fixes on the locked test sets. Use `train`/`dev`.
- Adding new `train` items is fine; changing test labels requires a documented
  re-lock and a bumped benchmark version.
- The **leakage rule** is non-negotiable: a duplicate or syndicated copy lives
  in exactly one split. If you touch split construction, run the leakage test.

The eval-regression gate in CI re-checks locked-split metrics; a regression
beyond tolerance fails the build.

## 5. Adding a new event type or entity type

Label spaces are the single source of truth in `naijafinsent/constants.py`
(`ENTITY_TYPES`, `EVENT_TYPES`, `EVENT_TYPE_DESCRIPTIONS`). To add a type:

1. **Update `constants.py`** — add the value (and, for events, a description).
2. **Update `naijafinsent/schemas.py`** — add the enum member. The module
   asserts that `SentimentLabel`/`EntityType`/`EventType` stay in sync with
   `constants.py`; a mismatch will fail at import.
3. **Update the annotation guide** — `docs/ANNOTATION_GUIDE.md`: definition,
   positive examples, negative examples, boundary rules vs existing types.
4. **Update the schema export** — re-export any JSON schema / label config the
   annotation tool and frontend consume so annotators can actually pick it.
5. **Update the tests** — constants↔schema sync tests; add an annotation-import
   test with the new label; update baselines/eval label maps.
6. **Update docs** — the entity/event tables in `docs/DATA_CARD.md` and the
   task sections in `docs/MODEL_CARD.md`.
7. **Re-annotate or backfill** — existing items do not gain the new type
   automatically; note coverage in the data card.

Do not rename or remove an existing type without a versioned re-lock; it
breaks comparability.

## 6. Running tests

```bash
pytest tests/ -q                                    # full suite
pytest tests/ -q -m "not slow and not network"      # fast, offline
pytest tests/test_architecture.py -q                # architecture rule
pytest tests/ -q --cov=naijafinsent                 # coverage
```

Markers: `slow`, `network` (network tests are deselected in CI by default).

## 7. Commit and PR conventions

**Commits** — imperative mood, scoped where useful:

```
feat(ner): add event-trigger span extraction
fix(api): cap batch size before model load
docs(model-card): record E2 delta placeholder
test(splits): assert duplicates stay in one split
```

**PR checklist:**

- [ ] Scope matches the PR title; no unrelated changes.
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `pytest tests/ -q` passes; architecture test included.
- [ ] No locked-test tuning.
- [ ] No article text, model weights, or secrets committed (§8).
- [ ] Docs updated if behaviour, labels, or numbers changed.
- [ ] Metrics are reported as measured with seed/variance, or left as a
      `TODO(measure)` placeholder — **never invented**.

## 8. Data-handling rules

Hard rules, enforced by review and pre-commit:

1. **Never commit article body text** for sources whose `license_note` does not
   permit redistribution. Only short evidence spans in fixtures are acceptable.
2. **Never commit trained models or weights** (`*.pt`, `*.bin`, `*.safetensors`,
   `*.joblib`, `*.onnx`) — `data/models/`, `data/corpus/`, `data/raw/`, and
   `data/processed/` are gitignored.
3. **Never commit secrets.** No API keys, tokens, or `.env` files. `gitleaks`
   and `detect-private-key` run in pre-commit.
4. **Respect source terms.** Honour `robots.txt`, rate limits, and each
   source's `license_note`; disable sources (`enabled=false`) when terms
   change.
5. **Keep provenance.** New sources enter via a manifest entry
   (`data/manifests/`) with the Stage 0 audit filled in.

See `data/README.md` for the directory layout and what is committed vs
ignored, and `docs/SOURCES.md` for the per-source access policy.

## 9. Reporting issues

Include: what you ran (exact command), what you expected, what happened, the
`AnalysisResult.status` (`complete`/`partial`/`failed`) and any stage-wise
provenance detail, plus environment (`python --version`, extras installed).
