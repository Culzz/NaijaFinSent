# Gold set (`data/annotation/gold/`)

`gold_set.jsonl` — 1,000+ labelled Nigerian financial sentences used by the
`goldset` evaluation gate (`scripts/eval_gate.py --gate goldset`).

## Annotator provenance — read this before quoting any number

Every label was produced by an **LLM-assisted pass** (`annotator:
"model-assisted-glm"`, `model_prelabel: true`). **No human being has confirmed
any label in this file.** This is the credibility roadmap's step 1 in its
honest interim form (the roadmap explicitly accepts "an LLM-assisted labelling
pass, with human review of a sample").

Consequently:

- The **Cohen's kappa** reported by the gate is the chance-corrected agreement
  between the assisted labels and the lexicon system. It is *not*
  inter-annotator agreement and never will be until two humans annotate.
- `gold_manifest.json` carries `inter_annotator_kappa: null` with that note.
- Numbers computed on this set are **model-assisted measurements**, not a human
  gold standard. A research claim that rests on them is provisional.

## Item composition

| Kind | Count | Meaning |
|---|---|---|
| `curated` | ~93 | Hand-style single sentences, written one by one |
| `templated_*` families | ~900 | Deterministic frames filled with real entities/values (`is_synthetic: true`) |

Template frames carry their labels by construction (the frame's polarity *is*
the label), so the templated subset measures **system coverage**, not
judgement. The curated subset is where label ambiguity lives.

`markers` tag the hard cases the roadmap calls out: `pidgin`, `naira_symbol`
(₦…), `naira_abbrev` (N… billion), `trn_bn_abbrev` (1.2trn), `kobo_format`,
`headline_fragment`, `ticker_collision`, `entity_paired` (sentence-level label
plus per-entity labels in `entity_sentiments`), and more. The gate breaks
accuracy down per marker.

## Splits (stated plainly)

The locked split views (`test_random`, `test_source`, `test_time`, frozen
`test`) are built by `naijafinsent.annotation.splits` from this pool (seed 7).
Because the gold set has no real publishers or dates yet:

- `publisher` = the generating family (`curated`, `templated_fx`, …);
- `published_at` = a synthetic date spread deterministically over the last year.

Both are recorded per item and openly synthetic. `test_source` therefore
measures held-out *style family*, and `test_time` held-out *synthetic month* —
useful plumbing while real corpus-backed labels do not exist.

The flat per-item `split` is the **random view** (`train` / `dev` /
`test_random`); membership in the held-out views is stored per item in
`split_views`. Exact counts are in `gold_manifest.json` → `split_sizes_flat`
and `split_view_sizes`.

## Review protocol (what turns this into a real gold set)

1. Two human annotators independently re-annotate a **stratified sample**
   (guideline: the full `curated` subset plus ≥200 templated items, sampled
   evenly across markers).
2. Compute genuine inter-annotator **Cohen's kappa** (the helper already lives
   in `naijafinsent/annotation/agreement.py`); adjudicate disagreements with
   majority vote + a written rationale.
3. Replace `sentiment.annotator` with real annotator ids and set
   `model_prelabel: false` for approved items.
4. Only then may the gate baseline treats itself as a quality gate rather than
   a coverage gate.

Regenerate deterministically with `python scripts/build_gold_set.py`.
