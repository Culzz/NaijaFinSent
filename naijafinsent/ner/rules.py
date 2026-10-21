"""Rule-based NER -- the honest, deterministic bootstrap baseline.

Combines:

* the lexicon matcher (:mod:`naijafinsent.preprocessing.lexicon`) for ORGs,
  PERs, regulators, sectors, and tickers;
* money regexes (:mod:`naijafinsent.preprocessing.naira`) for ``MONEY`` spans;
* a small set of regulator/ticker/currency patterns for anything the lexicon
  misses (e.g. an all-caps 3-6 letter ticker in an NGX context, ``CBN`` variants).

It is fast (no model load), deterministic (stable ordering), and makes no
confidence claims beyond a fixed per-source prior. It is the baseline a learned
tagger must beat.
"""

from __future__ import annotations

import re
from typing import Sequence

from naijafinsent.preprocessing.lexicon import Lexicon
from naijafinsent.preprocessing.naira import find_money_mentions
from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType
from naijafinsent.ner.base import BaseNerModel

__all__ = ["RuleBasedNer"]


# Regulator acronyms that may not be in a minimal lexicon.
_REGULATOR_PATTERN = re.compile(
    r"\b(?:CBN|SEC|NDIC|NGX|NSE|FCCPC|PenCom|PENCOM|NERC|FIRS|NCC|NDIC|"
    r"NAICOM|NIMC|FIRSR?|Federal\s+Inland\s+Revenue\s+Service|"
    r"Central\s+Bank\s+of\s+Nigeria)\b"
)

# An all-caps ticker-like token (2-8 letters/digits), used only when a ticker
# context word is nearby to avoid tagging every acronym.
_TICKER_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_TICKER_CONTEXT = re.compile(
    r"\b(?:NGX|NSE|ticker|shares?|stock|listed|equit(?:y|ies)|market|"
    r"price|gains?|rally|closed?)\b",
    re.IGNORECASE,
)

# Currency words/symbols for CURRENCY spans.
_CURRENCY_PATTERN = re.compile(
    r"(?:\u20a6|\$|\u00a3|\u20ac|\bNGN\b|\bUSD\b|\bGBP\b|\bEUR\b|"
    r"\bnaira\b|\bdollars?\b|\bpounds?\b|\beuros?\b|\bkobo\b)",
    re.IGNORECASE,
)

# Event trigger verbs/nouns (char-span level, cheapest useful set).
_EVENT_TRIGGER_PATTERN = re.compile(
    r"\b(?:raised?|cut|hiked?|held|declared|announced|acquired?|merged?|"
    r"sanctioned?|fined?|recapitalis(?:e|ed|ation)|recapitaliz(?:e|ed|ation)|"
    r"rights\s+issue|public\s+offer|profit|loss|dividend|earnings)\b",
    re.IGNORECASE,
)

# Fixed priors: rules are confident about money/currency/regulators, less so
# about ticker guesses.
_CONF = {
    EntityType.MONEY: 0.98,
    EntityType.CURRENCY: 0.95,
    EntityType.REGULATOR: 0.95,
    EntityType.TICKER: 0.70,
    EntityType.EVENT_TRIGGER: 0.60,
}


class RuleBasedNer(BaseNerModel):
    """Deterministic rule/lexicon NER for the NaijaFinSent entity types."""

    name = "rule-based-ner"
    version = "0.1.0"
    calibrated = False  # rule priors are not calibrated probabilities

    def __init__(
        self,
        *,
        lexicon: Lexicon | None = None,
        enable_ticker: bool = True,
        enable_event_triggers: bool = True,
        enable_currency: bool = True,
    ) -> None:
        self.lexicon = lexicon or Lexicon.from_file()
        self.enable_ticker = enable_ticker
        self.enable_event_triggers = enable_event_triggers
        self.enable_currency = enable_currency

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _add(spans: list[EntitySpan], span: EntitySpan, taken: list[tuple[int, int]]) -> None:
        """Append ``span`` if it does not overlap anything already taken."""
        for s, e in taken:
            if not (span.end <= s or span.start >= e):
                return
        taken.append((span.start, span.end))
        spans.append(span)

    def _regulator_spans(self, text: str) -> list[EntitySpan]:
        out: list[EntitySpan] = []
        for m in _REGULATOR_PATTERN.finditer(text):
            out.append(
                EntitySpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    entity_type=EntityType.REGULATOR,
                )
            )
        return out

    def _ticker_spans(self, text: str) -> list[EntitySpan]:
        out: list[EntitySpan] = []
        for m in _TICKER_PATTERN.finditer(text):
            window = text[max(0, m.start() - 40) : m.end() + 40]
            if _TICKER_CONTEXT.search(window):
                out.append(
                    EntitySpan(
                        start=m.start(), end=m.end(), text=m.group(0),
                        entity_type=EntityType.TICKER,
                    )
                )
        return out

    def _currency_spans(self, text: str) -> list[EntitySpan]:
        out: list[EntitySpan] = []
        for m in _CURRENCY_PATTERN.finditer(text):
            out.append(
                EntitySpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    entity_type=EntityType.CURRENCY,
                )
            )
        return out

    def _event_trigger_spans(self, text: str) -> list[EntitySpan]:
        out: list[EntitySpan] = []
        for m in _EVENT_TRIGGER_PATTERN.finditer(text):
            out.append(
                EntitySpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    entity_type=EntityType.EVENT_TRIGGER,
                )
            )
        return out

    # -- main -----------------------------------------------------------
    def predict(self, text: str) -> list[EntityPrediction]:
        """Return all rule-matched entity mentions, ordered by start offset."""
        if not text:
            return []

        spans: list[EntitySpan] = []
        taken: list[tuple[int, int]] = []

        # Priority 1: money (must win over currency symbol inside it).
        for span in find_money_mentions(text):
            self._add(spans, span, taken)

        # Priority 2: lexicon (orgs, people, regulators, sectors, tickers).
        for span in self.lexicon.match(text):
            self._add(spans, span, taken)

        # Priority 3: regex regulators not covered by the lexicon.
        for span in self._regulator_spans(text):
            self._add(spans, span, taken)

        # Priority 4: loose tickers in a market context.
        if self.enable_ticker:
            for span in self._ticker_spans(text):
                self._add(spans, span, taken)

        # Priority 5: currency mentions.
        if self.enable_currency:
            for span in self._currency_spans(text):
                self._add(spans, span, taken)

        # Priority 6: event triggers.
        if self.enable_event_triggers:
            for span in self._event_trigger_spans(text):
                self._add(spans, span, taken)

        spans.sort(key=lambda s: (s.start, s.end))
        return [
            EntityPrediction(
                span=s,
                confidence=_CONF.get(s.entity_type, 0.5),
                resolution_method="alias" if s.entity_type not in (
                    EntityType.MONEY, EntityType.CURRENCY, EntityType.EVENT_TRIGGER
                ) else None,
            )
            for s in spans
        ]

    def predict_batch(self, texts: Sequence[str]) -> list[list[EntityPrediction]]:
        return [self.predict(t) for t in texts]
