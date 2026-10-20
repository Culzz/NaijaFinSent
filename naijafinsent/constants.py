"""Shared vocabularies for the whole platform.

These are the single source of truth for label spaces. Annotation exports,
training code, the API, and the frontend all derive from these lists.
"""

from __future__ import annotations

# --- Document-level sentiment -------------------------------------------------
# "uncertain" is deliberately separate from "neutral": neutral means the text
# takes no position, uncertain means the text signals doubt/conditional outcome.
SENTIMENT_LABELS: tuple[str, ...] = ("positive", "negative", "neutral", "uncertain")
SENTIMENT_PRIMARY: str = "sentiment"  # document-level task name

# --- Entity types -------------------------------------------------------------
# Primary type only per span; a regulator is typed REGULATOR (its ORG-ness is
# implied, we never double-label a span).
ENTITY_TYPES: tuple[str, ...] = (
    "ORG",        # companies, banks, firms
    "PER",        # people
    "REGULATOR",  # CBN, SEC, NDIC, NERC, FCCPC, PENCOM ...
    "MONEY",      # monetary amounts (value+currency normalised separately)
    "TICKER",     # NGX ticker symbols: DANGCEM, MTNN, GTCO ...
    "CURRENCY",   # naira, dollar, euro mentions
    "SECTOR",     # banking, oil & gas, cement, telecoms ...
    "EVENT_TRIGGER",  # verbs/nouns that trigger an event frame
)

# --- Event taxonomy (6-8 types, v1) ------------------------------------------
EVENT_TYPES: tuple[str, ...] = (
    "cbn_policy",           # CBN policy decision (MPR, FX windows, circulars)
    "earnings",             # earnings / results / profit announcements
    "dividend",             # dividend declarations and payments
    "mna",                  # mergers, acquisitions, takeovers
    "regulatory_sanction",  # fines, sanctions, bans, penalties
    "capital_raise",        # capital raises, recapitalisation, rights issues
    "fx_move",              # FX / naira valuation moves, FX market policy
    "oil_energy",           # oil output, gas supply, energy disruption
)

EVENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "cbn_policy": "Central Bank of Nigeria policy decision, circular, or rate change",
    "earnings": "Company earnings, interim or final results",
    "dividend": "Dividend declaration, closure of registers, or payment",
    "mna": "Merger, acquisition, takeover, or divestment",
    "regulatory_sanction": "Regulatory fine, sanction, ban, or penalty",
    "capital_raise": "Capital raise, recapitalisation, rights issue, or public offer",
    "fx_move": "Foreign-exchange or naira valuation move / FX market policy",
    "oil_energy": "Oil output, gas supply, or energy-sector disruption",
}

# --- Source trust tiers (manifest) -------------------------------------------
TRUST_TIERS: tuple[str, ...] = ("official", "tier1", "tier2", "tier3", "unknown")
# official = CBN/SEC/NGX releases; tier1 = BusinessDay/Nairametrics/Punch/Premium Times

# --- Task names (used in model registry + eval reports) ----------------------
TASK_SENTIMENT = "sentiment"
TASK_NER = "ner"
TASK_EVENTS = "events"
TASK_ENTITY_SENTIMENT = "entity_sentiment"
