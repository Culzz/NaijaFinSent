# Limitations

Blunt list of what NaijaFinSent cannot do and where its numbers are weakest.
Read this before quoting any result.

> Not investment advice. No causal or predictive claim about prices or returns
> is made anywhere in this project.

---

## 1. Data limitations

### 1.1 Coverage skew
The corpus is a **sample**, not a census. It leans toward the publishers that
are audited and accessible (tier-1 outlets) and toward official releases.
Regional, vernacular, and small-press coverage is under-represented. Any
conclusion about "Nigerian financial news" is really a conclusion about
*this* sample.

### 1.2 English-only, effectively
The corpus is near-exclusively English (Nigerian English). Pidgin, Yoruba,
Hausa, and Igbo financial registers are scarcely present. This caps RQ4: an
Afro-centric model has no local-language signal to exploit, so a null result
for AfroXLM-R means "no local-language content", not "local models don't help".

### 1.3 Syndication and duplication
Wire and syndicated copy inflates apparent coverage. It is controlled by
hashing, MinHash, and `syndicated_from`, but dedup thresholds are heuristics:
some near-duplicates survive and some distinct stories are over-merged.

### 1.4 Small N
Annotated data is human-bounded. Counts are small, rare classes (e.g.
`uncertain` sentiment, rare event types) are very small, and per-slice
estimates are noisy. `<!-- TODO(measure): N per class and per slice -->`

### 1.5 Annotation subjectivity
Sentiment and event boundaries are judgement calls: sarcasm, mixed sentiment,
"neutral vs uncertain", and overlapping event types are genuinely ambiguous.
Agreement is measured (Cohen's κ, span F1) and reported — not assumed.

### 1.6 LLM pre-labelling risk
A share of labels began as LLM pre-labels, then received **mandatory human
review** (see `docs/DATA_CARD.md` §4.1). Risks: anchoring (reviewers defer to
the pre-label), systematic LLM biases entering the "gold" set, and circularity
if the same LLM is later evaluated on labels it helped create. Mitigations:
`model_prelabel` provenance flag, stratification, and a human-only vs
reviewed comparison. This remains a real limitation.

### 1.7 Temporal window
The collection window over-samples the ingested period(s). Models can latch
onto period-specific language (a particular FX regime, a particular MPR
cycle). The time-held-out split measures this, but cannot remove it.

## 2. Methodological limitations

### 2.1 Single domain
All data is Nigerian financial news/releases. Results do not transfer to other
African markets, other domains, or to spoken/vernacular financial language.

### 2.2 Temporal drift
Vocabulary and framing shift (policy regimes, ticker changes, rebrands). A
model trained on an earlier period drifts; the `test_time` gap quantifies this
but does not fix it.

### 2.3 Leakage risks and their controls
Leakage is the main threat to validity. Controls:

- Exact duplication removed by `content_hash`.
- Near-duplication removed/flagged by MinHash.
- Syndicated copies flagged and grouped.
- **Duplicates and syndicated copies live in exactly one split.**
- Source-held-out and time-held-out splits for generalization.
- Locked test labels, hash-pinned; never tuned on.

Residual risk: paraphrase and shared-source stories below the dedup threshold,
and shared entities/topics across splits that a model can exploit.

### 2.4 No causal inference
The system measures language in coverage. It does **not** and **cannot**
establish that coverage caused, predicted, or preceded a price move. No causal
claims are supported by this work.

### 2.5 Calibration limits
Probabilities are raw unless temperature-scaled on `dev`. Calibration
typically degrades on unseen publishers and rare classes; ECE on
`test_source` is expected to be worse than on `test_random`.
`<!-- TODO(measure): ECE by split -->`

### 2.6 Statistical power
With small N and ≥3 seeds, confidence intervals are wide. Differences smaller
than the CI overlap are **not** claims of improvement. Do not pick the best of
several seeds; report mean ± CI.

### 2.7 Entity resolution is bounded by its alias table
Resolution errs toward `ambiguous` when unsure. This is honest but reduces
recall; entities outside the alias table resolve poorly.

## 3. Product limitations

### 3.1 Not advice
The app presents language measurements, not recommendations. It is not
investment, legal, tax, or compliance advice.

### 3.2 No forecasting
No price, return, or event-frequency forecasting exists. Any future predictive
feature requires separate time-aware validation and leakage controls and is
out of scope.

### 3.3 Retrieval-based copilot can miss context
The copilot answers from retrieved corpus items. If retrieval misses the
relevant story, the answer is incomplete even when fluent. It is designed to
**abstain** when evidence is absent, which means it will decline questions a
human could answer from memory.

### 3.4 Evidence is per-article
Evidence spans show the sentence behind a prediction. A single article may
omit context from other coverage; the app does not reconcile across sources
into a single "truth".

## 4. What would change our conclusions

- **A local-language slice**: real Pidgin/Yoruba/Hausa/Igbo financial text
  would let us actually test RQ4 and could change the AfroXLM-R verdict.
- **Much larger annotation**: more labels would tighten CIs and let rare
  classes be evaluated meaningfully.
- **A true temporal hold-out far in the future**: would test drift beyond the
  observed window.
- **Publisher expansion**: more and more diverse sources would test whether
  the source-held-out gap is general or an artifact of which outlets we hold
  out.
- **Human-only labels**: a fully human-annotated subset would let us quantify
  and potentially overturn any LLM pre-labelling effect.
- **Chance-corrected agreement thresholds not met**: if κ falls below
  acceptable levels, the affected task's benchmark numbers should be treated
  as unreliable until the guide and labels are revised.

If any of these change the measured gaps, the corresponding claims in the
model card and case study must be updated, with the old numbers retained and
marked superseded.
