"""Rule / keyword event baseline.

This is the Stage 4 ``keyword rules`` baseline and also the deterministic model
used in the offline demo. Each event type has trigger patterns written from
Nigerian financial-journalism phrasing; a match produces one event carrying the
matched sentence as its evidence span.

Design notes
------------
* Patterns are anchored on lowercased text and are deliberately *precise*: a
  near-miss ("the bank may raise capital next year" when discussing a rumour)
  should not fire unless it names a concrete action verb.
* Attributes (amounts, direction, event date) are filled in by
  :mod:`naijafinsent.event_extraction.attributes`, not here, so extraction stays
  testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from naijafinsent.constants import EVENT_TYPE_DESCRIPTIONS
from naijafinsent.event_extraction.base import EventModelMixin, find_evidence_span
from naijafinsent.schemas import (
    EntityPrediction,
    EventPrediction,
    EventType,
    EvidenceSpan,
    ModelRef,
)


@dataclass(frozen=True)
class TriggerSpec:
    """A trigger pattern set for one event type."""

    event_type: EventType
    patterns: list[str]
    negative_patterns: list[str] = field(default_factory=list)


# Patterns are regex fragments matched case-insensitively against the sentence.
TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(
        EventType.CBN_POLICY,
        [
            r"\bmp\s?r\b.*\b(raise|rais|cut|hold|retain|hike|reduc|unchang|increase|lower)",
            r"\bmonetary policy (rate|committee|meeting)\b",
            r"\bcbn\b.*\b(raise|cut|hold|retain|hike|reduc|unchang|circular|directive|directed)\b",
            r"\bcentral bank of nigeria\b.*\b(raise|cut|hold|hike|reduc|policy|circular)\b",
            r"\b(cash reserve ratio|crr|liquidity ratio)\b",
            r"\bforeign exchange (window|policy|guideline|circular)\b",
        ],
        [
            r"\bcbn\b.*\bsaid it (may|might|could)\b",
            r"\banalysts (expect|predict|forecast)\b.*\bmp\s?r\b",
        ],
    ),
    TriggerSpec(
        EventType.EARNINGS,
        [
            r"\b(post(ed|s)?|report(ed|s)?|declar(ed|es)|announc(ed|es))\b.*\b(profit|revenue|earnings|results|turnover|gross|pre-tax|pat|pbt|loss)\b",
            r"\b(profit|revenue|earnings|turnover)\b.*\b(rose|fell|grew|declined|jumped|dropped|up|down|surged|slumped|increased|decreased)\b.*\b(percent|per cent|%|to n|to ₦)\b",
            r"\b(h1|h2|q1|q2|q3|q4|first half|full year|third quarter)\b.*\b(results|profit|revenue|earnings)\b",
            r"\bhalf[- ]year\b.*\b(results|profit|earnings)\b",
        ],
        [
            r"\b(profit|revenue)\b.*\b(is expected|is forecast|analysts expect|would be)\b",
        ],
    ),
    TriggerSpec(
        EventType.DIVIDEND,
        [
            r"\bdiv(,|.)?i?d(end|ends|end)\b",
            r"\binterim dividend\b",
            r"\bfinal dividend\b",
            r"\b(declare[ds]?|propose[ds]?|recommend(ed|s)?|approv(ed|es)|pay(s|able)?)\b.*\b(kobo|₦|n)\b.*\b(per share|dividend)\b",
            r"\bdividend\b.*\b(per share|kobo|yield|payment)\b",
            r"\bclosure of register\b",
        ],
    ),
    TriggerSpec(
        EventType.MNA,
        [
            r"\b(merg(er|es|ed|ing)|acquisition|acquire[ds]?|acquiring|takeover|take[- ]over)\b",
            r"\b(divest(ment|ed|s)?|divestiture)\b",
            r"\b(buy|bought|buys|acquired)\b.*\b(stake|shares|equity|majority|controlling)\b",
            r"\bstake\b.*\b(acqui|buy|purchas|sold|dispos)",
            r"\b(completion|completed)\b.*\b(merger|acquisition|transaction)\b",
        ],
    ),
    TriggerSpec(
        EventType.REGULATORY_SANCTION,
        [
            r"\b(fine[ds]?|fined|sanction(ed|s)?|penal(is|t)(ed|y|ies)|slammed)\b",
            r"\b(revok(ed|es|e)|suspend(ed|s|ing)|ban(ned|s|ning)|barred|seiz(ed|es))\b.*\b(licen[cs]e|permit|approval|operations?|account|registration)\b",
            r"\b(sec|ndic|nerc|fccpc|pencom|sfc|cbn)\b.*\b(fine|sanction|penalt|suspension|revok|barr)\b",
            r"\b(regulatory|regulator)\b.*\b(action|sanction|penalt|fine)\b",
        ],
    ),
    TriggerSpec(
        EventType.CAPITAL_RAISE,
        [
            r"\b(recapitalis|recapitaliz)(ation|e|ed|es|ing)\b",
            r"\b(rights? issue|public offer|private placement|initial public offer|ipo)\b",
            r"\b(capital raise|raise capital|raising capital|capital raising)\b",
            r"\b(share|equity|bond|eurobond|note[s]?)\b.*\b(issu(ed|ance|es|ing)|offer(ed|ing|s)|rais(ed|es|ing))\b",
            r"\b(cbn|central bank)\b.*\b(recapitalis|recapitaliz|minimum capital|capital base|capital adequacy)\b",
        ],
    ),
    TriggerSpec(
        EventType.FX_MOVE,
        [
            r"\bnaira\b.*\b(closed|fell|rose|depreciat|appreciat|strengthen|weaken|slid|gained|lost|fell to|hits?|hit)\b",
            r"\b(parallel market|black market|bureau de change|bdc|i&e window|nafex|official window|investors and exporters)\b",
            r"\b(exchange rate|fx rate|foreign exchange rate)\b.*\b(n|₦|\d)",
            r"\b(n|₦)\s?\d[\d,\.]*\b.*\b(dollar|usd|\$|pound|euro)\b",
            r"\b(dollar|usd)\b.*\b(n|₦)\s?\d[\d,\.]*\b",
        ],
        [
            r"\bnalira\b",  # guard against typos matching naira patterns
        ],
    ),
    TriggerSpec(
        EventType.OIL_ENERGY,
        [
            r"\b(crude oil|crude|bonny light|brent)\b.*\b(production|output|price|barrel|export|output|rise|fall|drop|gain)\b",
            r"\b(opec|nnpc|nuprc|dangote refinery|port harcourt refinery|warri refinery|kaduna refinery)\b",
            r"\b(oil|gas|petrol|pms|diesel|ago|electricity|power grid|megawatt|mw|disco|genco)\b.*\b(supply|shortage|disruption|output|production|price|hike|tariff|shutdown|vandal)\b",
            r"\b(pipeline vandalism|oil theft|force majeure|shut[- ]in|shutdown)\b",
            r"\b(petrol|pms|fuel)\b.*\b(price|subsidy|hike|increase|scarcity|queue)\b",
        ],
    ),
)

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    spec.event_type.value: [re.compile(p, re.IGNORECASE) for p in spec.patterns]
    for spec in TRIGGERS
}
_NEGATIVE: dict[str, list[re.Pattern[str]]] = {
    spec.event_type.value: [re.compile(p, re.IGNORECASE) for p in spec.negative_patterns]
    for spec in TRIGGERS
}


class KeywordEventModel(EventModelMixin):
    """Deterministic keyword baseline over the eight event types."""

    name = "keyword-events"
    version = "0.1.0"
    task = "events"
    calibrated = False

    def __init__(self, *, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _sentences(text: str) -> list[tuple[int, int, str]]:
        """Split into (start, end, sentence) triples with exact offsets."""
        out: list[tuple[int, int, str]] = []
        i = 0
        n = len(text)
        while i < n:
            j = i
            # Advance to the next sentence terminator followed by space/EOS.
            # A '.' immediately followed by a digit is inside a decimal number
            # ("50 basis points to 27.75 percent") — never a terminator.
            while j < n:
                ch = text[j]
                if ch == "." and j + 1 < n and text[j + 1].isdigit():
                    j += 1
                    continue
                if ch in ".!?\n":
                    break
                j += 1
            if j < n and text[j] in ".!?":
                j += 1
                while j < n and text[j] in "\"')]":
                    j += 1
            start, end = i, j
            while start < end and text[start] == " ":
                start += 1
            sent = text[start:end].strip()
            if sent:
                out.append((start, start + len(sent), sent))
            i = j if j > i else i + 1
        return out

    def _match_types(self, sentence: str) -> list[tuple[EventType, float]]:
        lower = sentence.lower()
        hits: list[tuple[EventType, float]] = []
        for spec in TRIGGERS:
            et = spec.event_type
            patterns = _COMPILED[et.value]
            matched = sum(1 for p in patterns if p.search(lower))
            if matched == 0:
                continue
            if any(p.search(lower) for p in _NEGATIVE[et.value]):
                continue
            # Confidence rises with the number of distinct patterns matched,
            # capped below 1.0 because a rule hit is never certain.
            conf = min(0.55 + 0.15 * (matched - 1), 0.9)
            hits.append((et, conf))
        return hits

    # -- public API ------------------------------------------------------
    def predict(
        self, text: str, entities: list[EntityPrediction] | None = None
    ) -> list[EventPrediction]:
        if not text or not text.strip():
            return []

        mentions = entities or []
        out: list[EventPrediction] = []
        seen: set[str] = set()

        for start, end, sentence in self._sentences(text):
            hits = self._match_types(sentence)
            if not hits:
                continue
            # Entities mentioned inside this sentence become the event's actors.
            local_entities = [
                e for e in mentions if e.span.start >= start and e.span.end <= end
            ]
            for et, conf in hits:
                key = f"{et.value}:{start}"
                if key in seen:
                    continue
                seen.add(key)
                if conf < self.min_confidence:
                    continue
                out.append(
                    EventPrediction(
                        event_type=et,
                        confidence=round(conf, 3),
                        event_date=None,  # filled by attributes.extract_event_date
                        entities=local_entities,
                        evidence=[EvidenceSpan(
                            text=text[start:end], start=start, end=end
                        )],
                        attributes={
                            "trigger": "keyword",
                            "description": EVENT_TYPE_DESCRIPTIONS.get(et.value, ""),
                            "sentence_index": next(
                                i for i, (s, _, _) in enumerate(
                                    self._sentences(text)
                                ) if s == start
                            ),
                        },
                        model=ModelRef(
                            name=self.name, version=self.version, task=self.task,
                            calibrated=self.calibrated,
                        ),
                    )
                )
        return out


__all__ = ["KeywordEventModel", "TriggerSpec", "TRIGGERS"]
