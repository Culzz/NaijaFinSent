# NaijaFinSent Annotation Guide

**Version:** 1.0 · **Effective:** 2026-10-20 · **Lexicon:** `data/annotation/lexicon.v1.json`

This is the single source of truth for every human label in NaijaFinSent. If the
guide and the code disagree, the guide wins and the code is a bug. The
machine-readable mirror of this document lives in
`naijafinsent/annotation/guidelines.py`; the validator
(`naijafinsent/annotation/validate.py`) enforces the rules stated here.

> A second annotator must be able to label from this document alone, without
> asking the first annotator questions. If you had to ask, the guide is
> incomplete and must be amended.

---

## 0. What we are labelling, and what we are not

NaijaFinSent measures the **language** of Nigerian financial journalism. We label:

1. **Document sentiment** — the position the text takes about its subject matter.
2. **Entities (NER)** — the named things in the text, plus money, tickers, sectors,
   and event triggers.
3. **Money normalisation** — the numeric value and currency behind every MONEY span.
4. **Events** — structured event frames (8 types) with an evidence span.
5. **Entity sentiment** — the stance the text takes towards one named entity.
6. **Event sentiment** — the evaluation the text places on one event frame (a
   sub-task; see §1.2).
7. **Market sentiment** — the direction the text claims for a market aggregate.

We do **not** make causal or predictive claims. A "positive" label means *the
text says something positive about the subject*, not *the price will go up*.

---

## 1. Sentiment

### 1.1 The four labels

| Label | Definition |
|---|---|
| `positive` | The text asserts a favourable position on its subject matter. |
| `negative` | The text asserts an unfavourable position on its subject matter. |
| `neutral` | The text takes **no** evaluative position on its subject matter. |
| `uncertain` | The text **does** take a position, but hedges, conditions, disputes, or leaves it open. |

### 1.2 Sentiment targets are SEPARATE tasks

Document, entity, event, and market sentiment are four distinct tasks. They are
never merged, and one label never "covers" two targets.

- **Document sentiment** — the position the *whole text* takes about its subject
  matter. It is **not** the reader's mood, **not** the market's reaction, **not**
  the tone of individual words. Example: *"Nigeria's inflation eased to 24.1% in
  September"* is `positive` even though every word is calm — the *claim* is
  favourable.
- **Entity sentiment** — the stance the text takes towards **one specific named
  entity**. Stored as a `SentimentAnnotation` with `task="entity_sentiment"` and
  a `target_entity`. Example: *"GTCO's profit fell 8%"* → document `negative`
  **and** entity sentiment `negative` **for GTCO** if that sentence is about GTCO.
  A single article can be positive for one entity and negative for another.
- **Event sentiment** — the evaluation the text places on **one event frame**.
  Example: *"Zenith declared a final dividend of N3.50 per share, below consensus"*
  → event `dividend`, event sentiment `negative` (below expectation), even if the
  document as a whole is `neutral`.
- **Market sentiment** — the direction the text claims for a **market aggregate**
  (equities, FX, bonds, oil). Requires an explicit market referent in the text.
  Example: *"The All-Share Index closed 0.4% higher"* → market sentiment
  `positive`. Absent an explicit market referent, do not assign market sentiment.

A record may carry several target kinds at once; each stored annotation names
**exactly one** target.

### 1.3 Neutral vs uncertain — the decision rule

> **Ask: does the text take a position on its subject?**
> - **No position** → `neutral`.
> - **A position that is hedged, conditional, disputed, or explicitly left open** → `uncertain`.
> - **Pros and cons balanced with no net direction** → `neutral`.
> - Never use `uncertain` to mean *"I, the annotator, am unsure."* The annotator's
>   uncertainty is a guide problem; the label describes the text.

### 1.4 Contrasting examples (neutral vs uncertain)

| # | Text | Label | Why |
|---|---|---|---|
| 1 | "The CBN will announce its MPR decision on Tuesday." | `neutral` | Schedule/fact; no evaluative position. |
| 2 | "MPR was held at 27.50%, as widely expected." | `neutral` | Reports a decision without evaluating it. |
| 3 | "Whether the MPR hold will slow inflation remains to be seen." | `uncertain` | Explicitly leaves the outcome open. |
| 4 | "Analysts are split on the naira's path over the next quarter." | `uncertain` | A position is at stake but the text refuses to resolve it. |
| 5 | "Revenue rose 12% but costs rose 15%, leaving profit roughly flat." | `neutral` | Balanced; no net direction, nothing unresolved. |
| 6 | "The bank's recapitalisation plan could either restore buffers or dilute existing holders." | `uncertain` | Both directions asserted, neither preferred. |
| 7 | "Operators warned that fuel queues may persist unless the dispute is resolved." | `uncertain` | Conditional negative; the negative is not asserted outright. |
| 8 | "GTCO's profit fell 8% year on year." | `negative` | An unfavourable fact is the subject matter. |

Examples 3, 4, 6, 7 are `uncertain`. Examples 1, 2, 5 are `neutral`. If you find
yourself placing a conditional sentence in `neutral`, re-read §1.3.

### 1.5 Sentiment decision rules (subset; full set in `guidelines.py`)

- **S1** — Label from what the text asserts, not from word tone.
- **S2** — No position = neutral; hedged position = uncertain.
- **S3** — Doubt / conditional / unresolved dispute → uncertain, never neutral.
- **S4** — Balanced pros and cons with no net direction → neutral.
- **S5** — A negative fact stated without evaluation still carries `negative` when
  the negative fact *is* the subject matter.
- **S6** — Do not infer sentiment from the presence of a MONEY span or a big number.

---

## 2. Entities (NER)

### 2.1 One primary type per span

Exactly **one** type per span. A regulator is typed `REGULATOR`; its ORG-ness is
implied and we never double-label. The eight types are:

| Type | Definition | Example |
|---|---|---|
| `ORG` | Company, bank, firm, cooperative, non-regulatory organisation. | `Dangote Cement` |
| `PER` | Named person. | `Olayemi Cardoso` |
| `REGULATOR` | Regulatory/supervisory body. | `CBN`, `SEC`, `NERC` |
| `MONEY` | Monetary amount span. | `₦2bn` |
| `TICKER` | Exchange ticker symbol. | `DANGCEM`, `MTNN` |
| `CURRENCY` | Currency mention that is not part of a monetary amount. | `naira`, `dollar` |
| `SECTOR` | Economic sector/sub-sector. | `banking`, `cement` |
| `EVENT_TRIGGER` | Word/phrase triggering an event frame. | `declared`, `fined`, `acquired` |

### 2.2 Entity rules

- **Nested spans are not permitted.** Where two candidates overlap, keep the
  **longest** span with a defensible single type and drop the shorter.
  - *"Central Bank of Nigeria Governor Olayemi Cardoso"* → one `PER` span
    (`Olayemi Cardoso`) plus one `REGULATOR` span (`Central Bank of Nigeria`);
    never a `REGULATOR` span that swallows the person.
- **Multi-word entities** stay whole: `Dangote Cement`, `FBN Holdings`,
  `Premium Times`, `Tier-2 capital`.
- **Headlines**: annotate mentions in the headline exactly as in the body. The
  headline is part of the item text and offsets are into the **full** item text.
- **Abbreviations**: annotate the abbreviated surface form where it appears and
  **do not expand** it in the span text. Expansion belongs to entity resolution.
  *"CBN"* is annotated as the literal span `CBN`; the canonical form lives in the
  lexicon, not in the span.
- **Tickers vs company names**: a ticker symbol is `TICKER`; a company name is
  `ORG`. A token that is both a common word and a ticker is `TICKER` **only** in an
  unambiguous market context. *"NB"* is `TICKER` in *"NB gained 2%"* but not when
  it means *nota bene*.
- **Duplicated mentions**: annotate **every** occurrence separately; repetition is
  not a violation. Only identical `(start, end, type)` triples collapse to one.
- **What NOT to annotate**: pronouns, generic nouns (`bank`, `company`, `market`),
  country names, bare dates, percentages, non-monetary numbers, punctuation.

---

## 3. Money normalisation

Keep the original span **verbatim**. Store the numeric `value`, the ISO-4217
`currency`, and the `unit` **only when stated**.

### 3.1 Rules

- **Never infer a missing unit.** `₦2bn` → value = `2.0`, unit = `billion`,
  currency = `NGN`. But `N2` with no scale word stays unit = `None`.
- **Never infer a missing currency.** A bare `2bn` with no currency symbol stays
  currency = `None`.
- **value and unit are separate.** Do not fold the scale into the value. `₦2bn`
  is value = 2.0, unit = `billion`; the notebook may compute a normalised amount
  downstream, but the stored `value` is the number as written.
- **Ranges**: `₦2–3bn` is annotated **once**. Store the low bound in `value` and
  the high bound in `value_high`, both scaled by `unit`. Never average the bounds.
- **`$40 oil` vs `$40m`**: `$40 oil` is USD 40 per barrel, unit = `None` (no scale
  word follows the number). `$40m` is USD 40, unit = `million`. The letters
  `m`/`bn`/`trn` bind to the number only when they **immediately follow** it.
- **Kobo**: kobo is 1/100 naira. `₦50kobo` → currency = `NGN`, unit = `kobo`,
  value = 50; it normalises to 0.50 naira.
- **Percentages are not money.** `12%` is never a MONEY span.

### 3.2 Worked examples

| Span text | value | unit | currency | Notes |
|---|---|---|---|---|
| `₦2bn` | 2.0 | billion | NGN | Sign + scale word. |
| `N2` | 2.0 | None | NGN | No scale word → unit stays None. |
| `NGN2.5trn` | 2.5 | trillion | NGN | ISO code prefix. |
| `naira 500` | 500.0 | None | NGN | Word currency, no scale. |
| `$40m` | 40.0 | million | USD | `m` binds to the number. |
| `$40` (oil price) | 40.0 | None | USD | No scale word → unit None. |
| `₦2–3bn` | 2.0 | billion | NGN | `value_high` = 3.0. |
| `₦50kobo` | 50.0 | kobo | NGN | Normalises to 0.50 naira. |
| `2bn` | 2.0 | billion | None | Currency not stated → stays None. |

---

## 4. Events

Eight event types. An event annotation **must** carry an `evidence_span` that
justifies it.

| Type | Definition |
|---|---|
| `cbn_policy` | CBN policy decision, circular, or rate change. |
| `earnings` | Company earnings, interim or final results. |
| `dividend` | Dividend declaration, register closure, or payment. |
| `mna` | Merger, acquisition, takeover, or divestment. |
| `regulatory_sanction` | Regulatory fine, sanction, ban, or penalty. |
| `capital_raise` | Capital raise, recapitalisation, rights issue, or public offer. |
| `fx_move` | FX / naira valuation move, or FX market policy. |
| `oil_energy` | Oil output, gas supply, or energy-sector disruption. |

### 4.1 Event date rule (explicit)

> **`event_date` is when the event HAPPENED, not the publish date.**
> If the text gives no date for the event, leave `event_date = None`. Never
> default it to `published_at` or to the annotation date.

### 4.2 Per-type examples

Each row gives a **positive** example with its evidence span, a **near-miss**,
and the shape of an **attribute** dict.

**`cbn_policy`**
- Positive: *"The MPC raised the MPR by 50bps to 27.50%."* — evidence:
  `raised the MPR by 50bps`.
- Near-miss: *"Analysts expect the MPC to hold rates."* — an expectation, not a
  decision.
- Attributes: `{"instrument": "MPR", "direction": "raise", "magnitude_bps": 50}`.

**`earnings`**
- Positive: *"GTCO reported a 34% rise in pre-tax profit."* — evidence:
  `reported a 34% rise in pre-tax profit`.
- Near-miss: *"GTCO will publish results next week."* — a forward-looking
  schedule, not a result.
- Attributes: `{"metric": "pre-tax profit", "change_pct": 34.0, "period": "FY2025"}`.

**`dividend`**
- Positive: *"Zenith declared a final dividend of N3.50 per share."* — evidence:
  `declared a final dividend of N3.50 per share`.
- Near-miss: *"The register closes on 12 March."* — a mechanical step, not a
  declaration.
- Attributes: `{"amount_per_share": 3.50, "currency": "NGN", "kind": "final"}`.

**`mna`**
- Positive: *"BUA agreed to acquire a majority stake in the target."* — evidence:
  `agreed to acquire a majority stake`.
- Near-miss: *"BUA is rumoured to be interested."* — a rumour, no agreement.
- Attributes: `{"acquirer": "BUA", "deal_value": None, "stake_pct": 51.0}`.

**`regulatory_sanction`**
- Positive: *"SEC fined the brokerage N10m."* — evidence: `fined the brokerage N10m`.
- Near-miss: *"SEC is investigating the brokerage."* — investigation open; no
  sanction yet.
- Attributes: `{"regulator": "SEC", "penalty": 10000000, "currency": "NGN"}`.

**`capital_raise`**
- Positive: *"The bank launched a N150bn rights issue."* — evidence:
  `launched a N150bn rights issue`.
- Near-miss: *"The bank could need fresh capital."* — speculation.
- Attributes: `{"amount": 150000000000.0, "currency": "NGN", "instrument": "rights issue"}`.

**`fx_move`**
- Positive: *"The naira weakened to N1,540/$ at the close."* — evidence:
  `weakened to N1,540/$`.
- Near-miss: *"The naira is quoted at the I&E window."* — venue description, not
  a move.
- Attributes: `{"pair": "USD/NGN", "rate": 1540.0, "direction": "weaken"}`.

**`oil_energy`**
- Positive: *"Crude output fell to 1.2mbpd in September."* — evidence:
  `output fell to 1.2mbpd`.
- Near-miss: *"OPEC+ meets next month."* — a meeting notice, no output change.
- Attributes: `{"commodity": "crude", "volume_mbpd": 1.2, "direction": "fall"}`.

### 4.3 General event rules

- An event annotation **must** carry an `evidence_span`.
- Multiple events may share one evidence span **only** if they are genuinely
  distinct frames asserted by that sentence.
- A forecast, expectation, rumour, or plan is **not** an event unless the text
  asserts the event has occurred or been formally decided.

---

## 5. Nigerian lexicon policy

### 5.1 Versioning

The terminology list is data: `data/annotation/lexicon.v1.json`. Adding terms
does **not** bump the version; changing a term's meaning, canonical form, or type
**does**. A version bump requires re-running the validator over affected records.

### 5.2 Acronym handling

Acronyms are annotated on **first and every** occurrence as their own span.
Expansion is a resolution-layer concern, not a span-layer one. The list we
maintain explicitly includes `CBN`, `MPR`, `NGX`, `SEC`, `NDIC`, `NERC`, `FCCPC`,
`PENCOM`, `FX`, `OMO`, `T-bills`, `MSCI`, `OPEC`.

### 5.3 Naira expressions

`₦`, `N`, `NGN`, `naira`, and `kobo` are all recognised. `₦` and `N` are the
naira symbol; `NGN` is the ISO code; `naira` is the word. All map to currency
`NGN`. `kobo` maps to `NGN` with unit `kobo` (1/100 naira). Ambiguity rule: a
bare `N` followed by a number in a financial article is naira; a bare `N` used as
a letter or name is not.

### 5.4 Pidgin and colloquial terms

Nigerian English and Pidgin finance terms are kept as lexicon entries and are
**not** silently translated. Examples: `wahala` (trouble), `japa` (emigrate),
`dey` (is/are/continuous marker), plus sector slang. These carry type `PIDGIN`.

### 5.5 `review_status` per term

Every term carries `review_status` ∈ {`reviewed`, `pending`}. A term is
`reviewed` **only** after a second person confirms its canonical form and type.
Anything uncertain — notably tickers — ships as `pending` until confirmed.

---

## 6. Span annotation rules

- **Tokenisation-agnostic.** Spans are character offsets, not token indices.
- **Offset convention:** inclusive `start`, exclusive `end`.
- **Whitespace:** spans never begin or end with whitespace; internal whitespace
  is preserved verbatim.
- **Normalisation:** offsets are into the NFKC-normalised, whitespace-collapsed
  item text stored in `AnnotationRecord.text`. Annotate the same string that will
  be exported.
- **Longest-match rule:** when overlapping candidates exist, keep the longest
  span whose type is unambiguous; drop shorter overlapping spans.
- **Overlaps:** spans of different types must never overlap. Equal offsets with
  the same type collapse to one.
- **What NOT to annotate:** pronouns, generic nouns, country names, bare dates,
  percentages, non-monetary numbers, punctuation.
- **Span length bounds:** 1–120 characters (validator-enforced).

---

## 7. Adjudication and IQA (inter-annotator quality assurance)

### 7.1 Process

1. **Double-annotation rate**: 15–20% of items, sampled stratified by label.
2. **Agreement gates**: document sentiment Cohen's κ ≥ 0.60; NER span-level F1 ≥
   0.70; event Cohen's κ ≥ 0.55. Below gate → guide revision + re-annotation.
3. **Resolution steps**:
   1. If annotators agree, accept.
   2. If not, both re-read the guide. If the rule is ambiguous, a third
      adjudicator decides **and the guide is amended**.
   3. If the item remains genuinely ambiguous after adjudication, mark it
      **unresolvable** and exclude it from test sets.

### 7.2 What counts as unresolvable

An item is **unresolvable** when competent annotators, applying the written rules
to the same text, cannot reach a stable label because the text is genuinely
ambiguous or self-contradictory. Unresolvable items:

- are recorded with a rationale,
- are **kept out of locked test splits**, and
- have their rate reported in the data card.

Every guide amendment is version-stamped in `GUIDELINES_VERSION` and must be
accompanied by re-annotation of affected items.

---

## 8. Quick workflow for a new annotator

1. Read §1.3 and §1.4 until you can place a conditional sentence correctly
   without the table.
2. Annotate entities with §2 open beside you; check every overlap against the
   longest-match rule.
3. Normalise money with §3; if you are tempted to guess a unit, stop — the answer
   is `None`.
4. For events, write the evidence span **first**, then choose the type from §4.
5. When a rule does not cover your case, flag the item and raise a guide
   amendment rather than inventing a convention.
