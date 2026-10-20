# Data Card — NaijaFinSent Corpus and Annotations

Following the *Datasheets for Datasets* structure (Gebru et al., 2021). This
card describes the corpus, the annotation layers, and the splits behind
NaijaFin-Bench.

| Field | Value |
|---|---|
| Dataset name | NaijaFinSent Corpus + NaijaFin-Bench annotations |
| Version | 1.0 (see §9 maintenance) |
| Language | English (Nigerian English), with some Pidgin/code-switched passages |
| Domain | Nigerian financial news and official releases |
| Maintainer | NaijaFinSent contributors |

> All sizes, counts, and agreement scores below are placeholders. Each names
> the script that produces it. Do not quote a number before it is measured.

---

## 1. Motivation

### 1.1 For what purpose was the dataset created?

To provide an open, provenance-tracked, locally annotated benchmark for
Nigerian financial NLP. No such public benchmark exists. Without it, claims
about sentiment, NER, or event-extraction quality on Nigerian financial text
are not comparable, and errors cannot be attributed to a data or modelling
cause.

### 1.2 Who created it and who funded it?

Created by NaijaFinSent contributors as an open research project. No external
funding is claimed. `<!-- TODO: confirm funding statement before public release -->`

### 1.3 Any other comments?

The corpus is built from published sources under their access terms. We
redistribute labels, URLs, and rebuild scripts — not article bodies — except
where a source's licence explicitly permits otherwise (§7).

## 2. Composition

### 2.1 What do the instances represent?

- **Corpus instances** are individual published items: Nigerian financial
  news articles and official releases (e.g. CBN/SEC/NGX releases). Each is an
  `Article` (`naijafinsent/schemas.py`) with provenance fields.
- **Annotation instances** are `AnnotationRecord`s: one per item, carrying
  document sentiment, entity spans, money normalisations, and events.

### 2.2 How many instances are there?

`<!-- TODO(measure): article count, per-publisher breakdown, official vs news'
-->
Produced by: `python -m naijafinsent.cli corpus stats` <!-- verify against --help -->

| Quantity | Value | Produced by |
|---|---|---|
| Total articles ingested | `<!-- TODO(measure) -->` | `python -m naijafinsent.cli corpus stats` |
| Articles after dedup | `<!-- TODO(measure) -->` | `python -m naijafinsent.cli dedupe && python -m naijafinsent.cli corpus stats` |
| Annotated items (all tasks) | `<!-- TODO(measure) -->` | `python -m naijafinsent.cli annotation stats` <!-- verify against --help --> |
| Double-annotated items | `<!-- TODO(measure) -->` (target 15–20%) | agreement report |
| Sentences/spans annotated | `<!-- TODO(measure) -->` | `naijafinsent.annotation` report |
| Official releases in corpus | `<!-- TODO(measure) -->` | `python -m naijafinsent.cli corpus stats --official` |

### 2.3 Does the dataset contain all possible instances, or is it a sample?

It is a **sample**, not a census. It is bounded by which sources are audited
and accessible, by the ingestion window, and by annotation capacity. Coverage
is skewed (§6.3).

### 2.4 What data does each instance consist of?

Per article: `url`, `canonical_url`, `title`, `publisher`, `source_id`,
`published_at`, `fetched_at`, `language`, `content` (stored locally; not
redistributed), `content_hash`, `is_official_release`, `syndicated_from`,
`is_duplicate`, `duplicate_of`, `minhash_signature`.

Per annotation: `item_id`, `article_id`, `split`, `text`, `sentiment`
(label, `target_entity`, `rationale_span`, `annotator`, `model_prelabel`),
`spans` (entity spans), `money` (value/currency/unit), `events` (event_type,
`event_date`, entities, `evidence_span`, `annotator`, `model_prelabel`).

### 2.5 Is there a label or target?

Yes — four supervised tasks plus an entity-resolution layer:

- Document sentiment (`SENTIMENT_LABELS`).
- Entity-level sentiment (per target entity).
- NER (`ENTITY_TYPES`).
- Event classification (`EVENT_TYPES`), with `event_date` and evidence.

### 2.6 Is any information missing?

- `published_at` is missing for some official releases.
- `event_date` is often unstated and is left `null` rather than inferred.
- Money `unit` is left `null` when not stated (we never infer a missing unit).
- `entity_id` is `null` for genuinely ambiguous mentions.

### 2.7 Are relationships between instances made explicit?

Yes. Every annotation references `article_id`. Duplicates reference
`duplicate_of`; syndicated copies reference `syndicated_from`. Entity mentions
resolve to canonical entities where `resolution_method` is not `ambiguous`.

### 2.8 Are there recommended data splits?

Yes — three locked test splits (§5).

### 2.9 Label spaces

**Entity types (8)** — `naijafinsent/constants.py` `ENTITY_TYPES`:

| Entity type | Meaning |
|---|---|
| `ORG` | Companies, banks, firms |
| `PER` | People |
| `REGULATOR` | CBN, SEC, NDIC, NERC, FCCPC, PENCOM … |
| `MONEY` | Monetary amounts (value + currency normalised separately) |
| `TICKER` | NGX ticker symbols: DANGCEM, MTNN, GTCO … |
| `CURRENCY` | Naira, dollar, euro mentions |
| `SECTOR` | Banking, oil & gas, cement, telecoms … |
| `EVENT_TRIGGER` | Verbs/nouns that trigger an event frame |

A span carries **one** primary type. A regulator is typed `REGULATOR` (its
org-ness is implied); we never double-label a span.

**Event types (8)** — `naijafinsent/constants.py` `EVENT_TYPES`:

| Event type | Description |
|---|---|
| `cbn_policy` | Central Bank of Nigeria policy decision, circular, or rate change |
| `earnings` | Company earnings, interim or final results |
| `dividend` | Dividend declaration, closure of registers, or payment |
| `mna` | Merger, acquisition, takeover, or divestment |
| `regulatory_sanction` | Regulatory fine, sanction, ban, or penalty |
| `capital_raise` | Capital raise, recapitalisation, rights issue, or public offer |
| `fx_move` | Foreign-exchange or naira valuation move / FX market policy |
| `oil_energy` | Oil output, gas supply, or energy-sector disruption |

**Sentiment labels (4):** `positive`, `negative`, `neutral`, `uncertain`.
`uncertain` is deliberately separate from `neutral`: `neutral` takes no
position; `uncertain` signals doubt or a conditional outcome.

## 3. Collection process

### 3.1 How was the data acquired?

Stage 0 is a **source audit** (`docs/SOURCES.md`). Each source is registered in
`data/manifests/` as a `SourceManifestEntry`: `source_id`, `name`, `base_url`,
`url_pattern`, `access_method` (`rss` | `sitemap` | `html` | `api`),
`license_note`, `trust_tier` (`official` | `tier1` | `tier2` | `tier3` |
`unknown`), `robots_checked_at`, `enabled`, `notes`.

Ingestion fetches via the declared method, using the configured `user_agent`
and respecting `fetch_rate_limit_seconds`, `fetch_max_bytes`,
`fetch_timeout_seconds`, and `fetch_max_redirects`. Text extraction uses
`trafilatura`/`lxml`. Non-HTML/text responses are rejected; scripts are never
executed; private/loopback/link-local addresses are blocked (SSRF protection).

### 3.2 What mechanisms or procedures were used to collect the data?

- Scheduled ingestion (`ingest_cron`) and on-demand CLI ingest.
- Deterministic content hashing (`sha256` of normalised content).
- Deduplication: exact by `content_hash`, near-duplicate by MinHash
  (`minhash_signature`), syndication flagged via `syndicated_from`.

### 3.3 Who collected the data, and how were they compensated?

NaijaFinSent contributors. `<!-- TODO: confirm compensation statement -->`
Annotation effort is voluntary/contributor time.

### 3.4 Over what timeframe was the data collected?

`<!-- TODO(measure): record ingestion start and end dates -->`
Produced by: `python -m naijafinsent.cli corpus stats` (min/max `fetched_at`).

### 3.5 Were ethical review processes conducted?

Not a human-subjects dataset; no IRB required. Article text is public
published journalism. Annotation is of text, not people. See §8 ethics.

## 4. Labelling process

### 4.1 How were labels produced? (**LLM pre-label + mandatory human review**)

This is disclosed explicitly:

1. **LLM pre-labelling (first pass).** An LLM proposes a first-pass label.
   This is **never** treated as gold.
2. **Mandatory human review.** A human reviewer accepts, edits, or rejects
   every pre-labelled item. No item reaches a locked split without human
   review.
3. **Provenance flag.** Every pre-labelled-then-reviewed item carries
   `model_prelabel = true` in `SentimentAnnotation` / `EventAnnotation`, so
   downstream analysis can stratify by provenance.
4. **Reportable comparison.** LLM-only agreement vs human-only and vs
   human-reviewed labels is measured, not assumed.

### 4.2 Who did the labelling? How were they instructed?

Contributors and reviewers, following `docs/ANNOTATION_GUIDE.md` (label
policy, edge cases: sarcasm, mixed sentiment, stated vs unstated units,
regulator vs org, ticker vs word collisions).

### 4.3 How was the quality of labels controlled?

- **Inter-annotator agreement** on a **15–20% double-annotated** sample:
  - Cohen's κ for categorical labels (sentiment, event type).
  - Span-level F1 for NER (strict span + type match), via `seqeval`.

`<!-- TODO(measure): report Cohen's κ and span F1 with N and CI -->
Produced by: `python -m naijafinsent.cli annotation agreement` <!-- verify against --help -->

### 4.4 Agreement targets

`<!-- TODO(measure): set after first double-annotation round. Provisional
targets: Cohen's κ ≥ 0.65 for sentiment, ≥ 0.70 for event type; span-level F1
≥ 0.80 for NER. -->`

## 5. Locked splits and the leakage rule

Three test splits are locked and hash-pinned in the split manifests under
`data/annotation/`:

| Split | Construction | Purpose |
|---|---|---|
| `test_random` | Stratified random hold-out | Standard benchmark number |
| `test_source` | Hold out entire publishers | Publisher generalization (RQ3) |
| `test_time` | Hold out the most recent period | Temporal generalization (RQ3) |

`train` and `dev` are disjoint from all three.

### 5.1 The leakage rule

> **A duplicate or syndicated copy lives in exactly one split.**

Exact duplicates (same `content_hash`) and near-duplicates (MinHash above
threshold) and syndicated copies (`syndicated_from`) are assigned to a single
split as a group. This applies across all three test splits and between
train/dev and test. The rule is enforced at split build time
(`python -m naijafinsent.cli splits build`) and checked by a leakage test.

## 6. Uses

### 6.1 What is the dataset intended for?

- Benchmarking sentiment, NER, entity-level sentiment, and event extraction on
  Nigerian financial text.
- Studying generalization across publishers and time.
- Training and comparing Nigeria-specific vs general vs finance-domain models.
- Building auditable, evidence-linked applications.

### 6.2 What should NOT be done with it?

- **Not investment advice.** No trading, portfolio, or advisory use.
- **No causal or predictive claims** about prices or returns.
- **No re-identification or profiling of individuals.**
- **No redistribution of article body text** where the source licence does not
  permit it.
- **No use of the locked test splits for training or hyper-parameter tuning.**
- **No treating LLM pre-labels as gold** or quoting corpus statistics without a
  source-provenance caveat.

### 6.3 Known biases and skews

- **Publisher skew:** tier-1 outlets dominate; smaller and regional outlets are
  under-represented.
- **English-only:** near-exclusively English; Pidgin, Yoruba, Hausa, and Igbo
  financial registers are under-represented, which caps any local-language
  claim (RQ4).
- **Urban/official-source skew:** coverage leans to Lagos/Abuja and official
  releases.
- **Macro-heavy:** CBN/FX/macro stories are over-represented relative to
  company-level reporting.
- **Temporal skew:** the collection window over-samples the period(s) ingested.
- **Label provenance skew:** a share of labels began as LLM pre-labels (§4.1).
- **Syndication:** wire/syndicated copy inflates apparent topic coverage unless
  deduped (it is).

`<!-- TODO(measure): publisher distribution table; official-vs-news ratio;
mean article length; language mix -->`

## 7. Licensing and redistribution

### 7.1 What we may redistribute

| Artifact | Redistributed? | Notes |
|---|---|---|
| Code | Yes — MIT | `LICENSE` covers code only |
| Labels (annotations) | Yes | Our contribution; released for research use |
| URLs and article IDs | Yes | Pointers, not content |
| Rebuild/ingest scripts | Yes | Reproduce the corpus yourself, subject to source ToS |
| Manifests with `license_note` | Yes | Per-source access policy |
| **Article body text** | **Only where the source licence permits** | Default: **not redistributed** |
| Official releases (CBN/SEC/NGX) | **Treated separately** | Often public; their own reuse terms apply |
| Corpus fixtures | Limited | Small, non-substitutable test fixtures only |

### 7.2 What this means in practice

We publish enough to **rebuild and verify** the benchmark without becoming a
mirror of copyrighted journalism. Any artifact that contains more than a short
evidence span for a non-permitted source is a bug — see `CONTRIBUTING.md`
data-handling rules and `docs/SOURCES.md`.

## 8. Ethics and legal

- **Not investment advice.** The dataset and any model trained on it measure
  language in published coverage. They make no claim about fundamentals and
  must not be used for trading or advisory decisions.
- **Copyright.** We respect source terms; we redistribute labels and pointers,
  not bodies, where not permitted.
- **Privacy.** Entities are public figures and organisations in published news.
  Private individuals' data is not a target of collection.
- **Harm.** The main misuse risk is financial decisions based on misread
  sentiment; this is mitigated by disclaimers, evidence links, and abstention
  in the copilot.

## 9. Maintenance and versioning

- **Versioning:** dataset versions are tagged (`v1.0`, `v1.1`, …) and split
  manifests are hash-pinned. Any change to a locked split increments the
  version and is noted in a changelog.
- **Corrections:** label corrections are versioned; locked test labels change
  only with a documented re-lock and a bumped benchmark version. Adding new
  `train` items is allowed without re-locking the test sets.
- **Adding sources:** new sources enter via the Stage 0 audit and a manifest
  entry; the corpus is rebuilt and deduped.
- **Retirement:** sources whose terms change are disabled (`enabled=false`)
  and excluded from future builds; historical labels remain but are flagged.
- **Cadence:** corpus refreshed on `ingest_cron`; benchmark re-released when
  models or slices change.

## 10. Producing each number in this card

| Number | Command |
|---|---|
| Corpus counts, date range, language mix | `python -m naijafinsent.cli corpus stats` |
| Dedup / syndication counts | `python -m naijafinsent.cli dedupe` then `corpus stats` |
| Annotation counts, provenance split | `python -m naijafinsent.cli annotation stats` <!-- verify against --help --> |
| Agreement (κ, span F1) | `python -m naijafinsent.cli annotation agreement` <!-- verify against --help --> |
| Split sizes / leakage check | `python -m naijafinsent.cli splits build && python -m naijafinsent.cli splits verify` <!-- verify against --help --> |
| Publisher distribution | `python -m naijafinsent.cli corpus stats --by publisher` <!-- verify against --help --> |
