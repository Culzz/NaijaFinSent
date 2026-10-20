"""Machine-readable annotation policy.

This module is the executable mirror of ``docs/ANNOTATION_GUIDE.md``. The
validator (``validate.py``), the export tools (``schema_export.py``), the
pre-labeller (``prelabel.py``), and the review UI all import from here so the
label space and the decision rules cannot drift between prose, tooling, and
code.

Nothing in this module touches the network or the filesystem: it is pure data
plus a handful of tiny lookup helpers, so it is safe to import anywhere.
"""

from __future__ import annotations

from typing import Any

from naijafinsent.constants import (
    ENTITY_TYPES,
    EVENT_TYPE_DESCRIPTIONS,
    EVENT_TYPES,
    SENTIMENT_LABELS,
    TRUST_TIERS,
)

# --------------------------------------------------------------------------
# Version / provenance
# --------------------------------------------------------------------------

GUIDELINES_VERSION = "1.0"
LEXICON_VERSION = "1.0"
GUIDELINES_EFFECTIVE_DATE = "2026-10-20"

# --------------------------------------------------------------------------
# Sentiment targets
# --------------------------------------------------------------------------
# Document / entity / event / market sentiment are SEPARATE tasks. A record
# may carry more than one target kind, but a single label never "covers" two
# targets: each stored annotation names exactly one target.

SENTIMENT_TARGETS: tuple[str, ...] = (
    "document",
    "entity",
    "event",
    "market",
)

SENTIMENT_TARGET_DESCRIPTIONS: dict[str, str] = {
    "document": (
        "The position the text as a whole takes about its subject matter. "
        "Not the reader's mood, not the market's reaction."
    ),
    "entity": (
        "The stance the text takes towards one specific named entity "
        "(company, person, regulator). Stored with target_entity."
    ),
    "event": (
        "The evaluation the text places on one specific event frame "
        "(e.g. a dividend cut is negative for holders). Keyed to an event_type."
    ),
    "market": (
        "The direction the text claims for a market aggregate (equities, "
        "FX, bonds, oil). Requires an explicit market referent in the text."
    ),
}

SENTIMENT_DECISION_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "S1",
        "rule": (
            "Label document sentiment from what the text asserts, not from the "
            "emotional tone of its words."
        ),
        "example": "Nigeria's inflation eased to 24.1% in September.",
        "label": "positive",
        "note": "The direction of the claim (easing) is positive, though the IST word is calm.",
    },
    {
        "id": "S2",
        "rule": (
            "Neutral means the text takes NO evaluative position on its subject. "
            "Uncertain means the text DOES take a position but conditions or hedges it."
        ),
        "example": "The CBN will announce its MPR decision on Tuesday.",
        "label": "neutral",
        "note": "A pure fact / schedule. No position, no doubt about a position.",
    },
    {
        "id": "S3",
        "rule": (
            "If the only evaluative content is doubt, a conditional outcome, or an "
            "unresolved disagreement, label uncertain — never neutral."
        ),
        "example": "Analysts are split on whether the naira will hold below N1,500/$.",
        "label": "uncertain",
        "note": "There is an evaluative stake but the text refuses to resolve it.",
    },
    {
        "id": "S4",
        "rule": (
            "If positive and negative framings are balanced with no dominant "
            "direction, label neutral."
        ),
        "example": "Revenue rose 12% but costs rose 15%, leaving profit roughly flat.",
        "label": "neutral",
        "note": "Balanced; no net position. Not uncertain — nothing is unresolved.",
    },
    {
        "id": "S5",
        "rule": (
            "A negative fact stated without evaluation still carries a negative "
            "document label when the subject matter is the negative fact."
        ),
        "example": "GTCO's profit fell 8% year on year.",
        "label": "negative",
        "note": "Reported decline in the subject's own headline metric.",
    },
    {
        "id": "S6",
        "rule": (
            "Do not infer document sentiment from the mere presence of a MONEY "
            "span or a big number."
        ),
        "example": "The bank raised N50bn in tier-2 capital in July.",
        "label": "neutral",
        "note": "A capital raise is a fact; whether it is good/bad is not asserted here.",
    },
)

NEUTRAL_VS_UNCERTAIN_RULE: str = (
    "Ask: does the text take a position on its subject? No position -> neutral. "
    "A position that is hedged, conditional, disputed, or explicitly left open -> "
    "uncertain. Balanced pros and cons with no net direction -> neutral. "
    "Never use uncertain as a synonym for 'I, the annotator, am unsure'."
)

NEUTRAL_VS_UNCERTAIN_EXAMPLES: tuple[dict[str, str], ...] = (
    {
        "text": "The CBN will announce its MPR decision on Tuesday.",
        "label": "neutral",
        "why": "Schedule/fact; no evaluative position taken.",
    },
    {
        "text": "MPR was held at 27.50%, as widely expected.",
        "label": "neutral",
        "why": "Reports a decision without evaluating it.",
    },
    {
        "text": "Whether the MPR hold will slow inflation remains to be seen.",
        "label": "uncertain",
        "why": "Explicitly leaves the outcome open.",
    },
    {
        "text": "Analysts are split on the naira's path over the next quarter.",
        "label": "uncertain",
        "why": "A position is at stake but the text refuses to resolve it.",
    },
    {
        "text": "Revenue rose 12% but costs rose 15%, leaving profit roughly flat.",
        "label": "neutral",
        "why": "Balanced; no net direction, nothing unresolved.",
    },
    {
        "text": "The bank's recapitalisation plan could either restore buffers or "
        "dilute existing holders.",
        "label": "uncertain",
        "why": "Both directions asserted, neither preferred.",
    },
    {
        "text": "Operators warned that fuel queues may persist unless the dispute is resolved.",
        "label": "uncertain",
        "why": "Conditional negative; the negative is not asserted outright.",
    },
)

# --------------------------------------------------------------------------
# Entity policy
# --------------------------------------------------------------------------

ENTITY_TYPE_DESCRIPTIONS: dict[str, str] = {
    "ORG": "A company, bank, firm, cooperative, or other non-regulatory organisation.",
    "PER": "A named person (full name, surname-only mention, or title+name).",
    "REGULATOR": (
        "A regulatory or supervisory body. Typed REGULATOR, never also ORG: "
        "the ORG-ness is implied by the primary type."
    ),
    "MONEY": "A monetary amount span (value+currency normalised separately).",
    "TICKER": "An NGX (or other exchange) ticker symbol, e.g. DANGCEM, MTNN, GTCO.",
    "CURRENCY": "A currency mention that is not part of a monetary amount, e.g. naira, dollar.",
    "SECTOR": "An economic sector or sub-sector, e.g. banking, cement, telecoms.",
    "EVENT_TRIGGER": "The word/phrase that triggers an event frame, e.g. declared, fined, acquired.",
}

ENTITY_POLICY: dict[str, Any] = {
    "one_primary_type_per_span": True,
    "longest_match_rule": True,
    "nesting": (
        "Nested spans are not permitted. Where two candidate spans overlap, keep "
        "the longest span that has a defensible single type and drop the shorter."
    ),
    "headlines": (
        "Annotate entity mentions in the headline exactly as in the body; the "
        "headline is part of the item text and offsets are into the full item text."
    ),
    "abbreviations": (
        "Annotate the abbreviated surface form where it appears and do not expand "
        "it in the span text. Expansion belongs to the lexicon/entity resolution layer."
    ),
    "tickers_vs_names": (
        "A ticker symbol is TICKER; a company name is ORG. A token that is both a "
        "common word and a ticker is TICKER only in an unambiguous market context."
    ),
    "do_not_annotate": (
        "Generic nouns (bank, company, market), country names, dates, percentages, "
        "non-monetary numbers, and pronouns are not annotated."
    ),
    "deduplicate_identical_offsets": True,
    "duplicated_mentions": (
        "Every occurrence is annotated separately. Repeating a mention is not a "
        "violation; only identical (start, end, type) triples are collapsed."
    ),
}

# --------------------------------------------------------------------------
# Money normalisation policy
# --------------------------------------------------------------------------

ALLOWED_CURRENCIES: tuple[str, ...] = ("NGN", "USD", "GBP", "EUR", "JPY", "ZAR", "XOF", "GHS")

CURRENCY_SYMBOLS: dict[str, str] = {
    "\u20a6": "NGN",  # naira sign
    "$": "USD",
    "\u00a3": "GBP",
    "\u20ac": "EUR",
    "\u00a5": "JPY",
}

MULTIPLIER_UNITS: dict[str, float] = {
    "hundred": 1e2,
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "m": 1e6,
    "billion": 1e9,
    "bn": 1e9,
    "trillion": 1e12,
    "tn": 1e12,
}

MONEY_POLICY: dict[str, Any] = {
    "keep_original_verbatim": True,
    "never_infer_missing_unit": True,
    "never_infer_missing_currency": True,
    "unit_and_value_are_separate": (
        "value is the numeric multiplier as written; unit is the stated scale word. "
        "Do not fold the multiplier into value: '\u20a62bn' is value=2.0, unit='billion', "
        "currency='NGN' and may also carry normalised_value=2e9 downstream."
    ),
    "unit_only_when_stated": (
        "'\u20a62' with no scale word keeps unit=None. A bare 'N2' is value=2.0, unit=None, "
        "currency='NGN'."
    ),
    "ranges": (
        "'\u20a62\u20133bn' is annotated once. Store the low bound in value and the high "
        "bound in value_high (both scaled by unit). Never average the bounds."
    ),
    "currency_disambiguation": (
        "'$40 oil' is USD 40 per barrel with unit=None (no scale word). '$40m' is "
        "USD 40 with unit='million'. 'm'/'bn'/'trn' bind to the number only when they "
        "immediately follow it."
    ),
    "kobo": (
        "kobo is 1/100 naira. '\u20a650kobo' is currency=NGN, unit='kobo', value=50 and "
        "normalises to 0.50 naira."
    ),
    "percentages_are_not_money": True,
}

# --------------------------------------------------------------------------
# Event taxonomy
# --------------------------------------------------------------------------
# Re-exported descriptions plus annotator-facing policy per event type.

EVENT_POLICY: dict[str, dict[str, Any]] = {
    "cbn_policy": {
        "definition": EVENT_TYPE_DESCRIPTIONS["cbn_policy"],
        "positive": [
            ("The MPC raised the MPR by 50bps to 27.50%.", "raised the MPR by 50bps"),
            ("CBN directed banks to cap cash withdrawals.", "directed banks to cap cash withdrawals"),
        ],
        "near_miss": [
            ("Analysts expect the MPC to hold rates.", "expectation, not a decision"),
        ],
        "attributes": {"instrument": "MPR", "direction": "raise", "magnitude_bps": 50},
    },
    "earnings": {
        "definition": EVENT_TYPE_DESCRIPTIONS["earnings"],
        "positive": [
            ("GTCO reported a 34% rise in pre-tax profit.", "reported a 34% rise in pre-tax profit"),
        ],
        "near_miss": [
            ("GTCO will publish results next week.", "forward-looking schedule, not a result"),
        ],
        "attributes": {"metric": "pre-tax profit", "change_pct": 34.0, "period": "FY2025"},
    },
    "dividend": {
        "definition": EVENT_TYPE_DESCRIPTIONS["dividend"],
        "positive": [
            ("Zenith declared a final dividend of N3.50 per share.", "declared a final dividend of N3.50 per share"),
        ],
        "near_miss": [
            ("The register closes on 12 March.", "mechanical step; not itself a declaration"),
        ],
        "attributes": {"amount_per_share": 3.50, "currency": "NGN", "kind": "final"},
    },
    "mna": {
        "definition": EVENT_TYPE_DESCRIPTIONS["mna"],
        "positive": [
            ("BUA agreed to acquire a majority stake in the target.", "agreed to acquire a majority stake"),
        ],
        "near_miss": [
            ("BUA is rumoured to be interested.", "rumour, no agreement asserted"),
        ],
        "attributes": {"acquirer": "BUA", "deal_value": None, "stake_pct": 51.0},
    },
    "regulatory_sanction": {
        "definition": EVENT_TYPE_DESCRIPTIONS["regulatory_sanction"],
        "positive": [
            ("SEC fined the brokerage N10m.", "fined the brokerage N10m"),
        ],
        "near_miss": [
            ("SEC is investigating the brokerage.", "investigation open; no sanction yet"),
        ],
        "attributes": {"regulator": "SEC", "penalty": 10_000_000, "currency": "NGN"},
    },
    "capital_raise": {
        "definition": EVENT_TYPE_DESCRIPTIONS["capital_raise"],
        "positive": [
            ("The bank launched a N150bn rights issue.", "launched a N150bn rights issue"),
        ],
        "near_miss": [
            ("The bank could need fresh capital.", "speculation, no raise announced"),
        ],
        "attributes": {"amount": 150e9, "currency": "NGN", "instrument": "rights issue"},
    },
    "fx_move": {
        "definition": EVENT_TYPE_DESCRIPTIONS["fx_move"],
        "positive": [
            ("The naira weakened to N1,540/$ at the close.", "weakened to N1,540/$"),
        ],
        "near_miss": [
            ("The naira is quoted at the I&E window.", "venue description, not a move"),
        ],
        "attributes": {"pair": "USD/NGN", "rate": 1540.0, "direction": "weaken"},
    },
    "oil_energy": {
        "definition": EVENT_TYPE_DESCRIPTIONS["oil_energy"],
        "positive": [
            ("Crude output fell to 1.2mbpd in September.", "output fell to 1.2mbpd"),
        ],
        "near_miss": [
            ("OPEC+ meets next month.", "meeting notice; no output change stated"),
        ],
        "attributes": {"commodity": "crude", "volume_mbpd": 1.2, "direction": "fall"},
    },
}

EVENT_DATE_RULE: str = (
    "event_date is when the EVENT HAPPENED, not the publish date. If the text "
    "gives no date for the event, leave event_date = None; do NOT default it to "
    "published_at or to the annotation date."
)

EVENT_GENERAL_RULES: tuple[str, ...] = (
    "An event annotation MUST carry an evidence_span that justifies it.",
    "Multiple events may share one evidence span only if they are genuinely distinct "
    "frames asserted by that sentence.",
    "A forecast, expectation, rumour, or plan is not an event unless the text asserts "
    "the event has occurred or been formally decided.",
    "event_date uses the event time, never the publication time.",
)

# --------------------------------------------------------------------------
# Span annotation rules
# --------------------------------------------------------------------------

SPAN_RULES: dict[str, Any] = {
    "tokenisation_agnostic": True,
    "offset_convention": "inclusive start, exclusive end",
    "whitespace": (
        "Spans never begin or end with whitespace. Internal whitespace is preserved "
        "verbatim from the source text."
    ),
    "normalisation": (
        "Offsets are into the NFKC-normalised, whitespace-collapsed item text stored "
        "in AnnotationRecord.text. Annotate the same string that will be exported."
    ),
    "longest_match": (
        "When overlapping candidates exist, keep the longest span whose type is "
        "unambiguous; drop shorter overlapping spans."
    ),
    "overlaps": "Spans of different types must never overlap. Equal offsets with the same type collapse to one.",
    "min_span_chars": 1,
    "max_span_chars": 120,
    "do_not_annotate": (
        "Pronouns, generic nouns, country names, bare dates, percentages, "
        "non-monetary numbers, and sentence punctuation."
    ),
}

# --------------------------------------------------------------------------
# Validation constants
# --------------------------------------------------------------------------

VALIDATION_CONSTANTS: dict[str, Any] = {
    "min_span_chars": 1,
    "max_span_chars": 120,
    "allowed_currencies": ALLOWED_CURRENCIES,
    "allowed_units": tuple(MULTIPLIER_UNITS) + ("kobo",),
    "allowed_sentiment_labels": SENTIMENT_LABELS,
    "allowed_entity_types": ENTITY_TYPES,
    "allowed_event_types": EVENT_TYPES,
    "allowed_trust_tiers": TRUST_TIERS,
    "allow_span_overlap": False,
    "require_event_evidence": True,
    "require_money_unit_only_when_stated": True,
    "max_events_per_record": 25,
    "max_spans_per_record": 400,
    "entity_sentiment_requires_target": True,
}

# --------------------------------------------------------------------------
# Lexicon policy
# --------------------------------------------------------------------------

LEXICON_POLICY: dict[str, Any] = {
    "versioning": (
        "The terminology list is versioned as data/annotation/lexicon.vN.json. "
        "A term's meaning change requires a version bump; adding terms does not."
    ),
    "acronyms": (
        "Acronyms (CBN, MPR, NGX, SEC, NDIC, NERC, FCCPC, PENCOM, FX, OMO, MSCI, OPEC) "
        "are annotated on first and every occurrence as their own span; expansion is a "
        "resolution-layer concern, not a span-layer one."
    ),
    "nih": (
        "Nigerian English and Pidgin finance terms (japa, wahala, dey, sabi) are kept "
        "as lexicon entries; do not silently translate them."
    ),
    "review_status_values": ("reviewed", "pending"),
    "review_status_rule": (
        "A term is 'reviewed' only after a second person confirms the canonical form "
        "and type. Anything uncertain (notably tickers) ships as 'pending'."
    ),
}

# --------------------------------------------------------------------------
# Adjudication / IQA
# --------------------------------------------------------------------------

ADJUDICATION_PROCESS: dict[str, Any] = {
    "double_annotation_rate": "15-20% of items, sampled stratified by label.",
    "agreement_gates": {
        "sentiment_cohens_kappa_min": 0.60,
        "ner_span_f1_min": 0.70,
        "event_cohens_kappa_min": 0.55,
    },
    "resolution_steps": (
        "1) If annotators agree, accept. 2) If not, both re-read the guide; if the "
        "rule is ambiguous, a third adjudicator decides and the guide is amended. "
        "3) If the item remains genuinely ambiguous after adjudication, mark it "
        "unresolvable and exclude it from test sets."
    ),
    "unresolvable_definition": (
        "An item is unresolvable when competent annotators, applying the written "
        "rules to the same text, cannot reach a stable label because the text is "
        "genuinely ambiguous or self-contradictory."
    ),
    "unresolvable_handling": (
        "Record it with a rationale, keep it out of locked test splits, and report "
        "the unresolvable rate in the data card."
    ),
    "amendments": (
        "Every guide amendment is version-stamped in GUIDELINES_VERSION and must be "
        "accompanied by re-annotation of affected items."
    ),
}


# --------------------------------------------------------------------------
# Lookup helpers
# --------------------------------------------------------------------------

def entity_description(entity_type: str) -> str:
    """Return the annotator-facing definition for an entity type."""
    return ENTITY_TYPE_DESCRIPTIONS.get(entity_type, "Unknown entity type.")


def event_description(event_type: str) -> str:
    """Return the annotator-facing definition for an event type."""
    return EVENT_TYPE_DESCRIPTIONS.get(event_type, "Unknown event type.")


def sentiment_target_description(target: str) -> str:
    """Return the definition of a sentiment target kind."""
    return SENTIMENT_TARGET_DESCRIPTIONS.get(target, "Unknown sentiment target.")


def all_decision_rules() -> tuple[dict[str, Any], ...]:
    """All sentiment decision rules, in rule-id order."""
    return SENTIMENT_DECISION_RULES
