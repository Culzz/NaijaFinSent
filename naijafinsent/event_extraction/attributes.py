"""Event attribute extraction: dates, values, direction, entity roles.

The single most important rule in this module is that **the event date is not
the publish date**. A story published on 2026-02-20 may report a CBN decision
taken on 2026-02-19, or a dividend that will be paid in April. Every function
here therefore takes ``publish_date`` as an argument and returns both dates,
clearly separated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from naijafinsent.schemas import EntityPrediction

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)
_MONTH_RE = rf"(?P<month>{_MONTHS})\.?"

# Named groups keep the three date shapes easy to read and hard to mis-index.
_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 19 February 2026 / 19 Feb 2026
    re.compile(rf"\b(?P<day>\d{{1,2}})\s+{_MONTH_RE}\s+(?P<year>\d{{4}})\b", re.I),
    # February 19, 2026
    re.compile(rf"\b{_MONTH_RE}\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b", re.I),
    # 2026-02-19
    re.compile(r"\b(?P<year>\d{4})-(?P<month_num>\d{2})-(?P<day>\d{2})\b"),
    # 19/02/2026 (day-first, the Nigerian convention)
    re.compile(r"\b(?P<day>\d{1,2})/(?P<month_num>\d{1,2})/(?P<year>\d{4})\b"),
)

_MONTH_NAME_TO_NUM = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_RELATIVE = {
    "yesterday": -1,
    "today": 0,
    "tomorrow": 1,
    "last week": -7,
    "next week": 7,
    "last month": -30,
    "next month": 30,
}
_QUARTER_RE = re.compile(r"\bq([1-4])\s*(\d{4})\b", re.IGNORECASE)

_RAISE = re.compile(
    r"\b(raise[ds]?|raised|hike[ds]?|increase[ds]?|increased|up|higher|"
    r"jack(ed|s)?|surge[ds]?)\b", re.IGNORECASE
)
_CUT = re.compile(
    r"\b(cut[s]?|lower(ed|s)?|reduce[ds]?|reduction|slash(ed|es)?|down|"
    r"decline[ds]?|fell|drop(ped|s)?|fall|slump(ed|s)?)\b", re.IGNORECASE
)
_HOLD = re.compile(
    r"\b(holds?|held|retain(ed|s)?|unchanged|leave[s]? unchanged|maintain(ed|s)?)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedAttributes:
    """Attributes attached to one event mention."""

    event_date: date | None
    publish_date: date | None
    date_basis: str  # "absolute" | "relative" | "quarter" | "unknown"
    direction: str | None  # "raise" | "cut" | "hold"
    values: list[dict]  # money/percent mentions with their spans
    actor_roles: dict[str, list[str]]


def extract_event_date(
    text: str,
    *,
    publish_date: date | datetime | None = None,
    span: tuple[int, int] | None = None,
) -> tuple[date | None, str]:
    """Extract the date an event happened, plus how it was derived.

    Returns ``(event_date, basis)`` where basis is one of
    ``absolute``, ``relative``, ``quarter``, or ``unknown``.
    """
    snippet = text if span is None else text[span[0] : span[1]]
    lowered = snippet.lower()

    # 1. Absolute dates, most specific first.
    for pattern in _DATE_PATTERNS:
        m = pattern.search(snippet)
        if not m:
            continue
        groups = m.groupdict()
        try:
            year = int(groups["year"])
            day = int(groups["day"])
            if groups.get("month_num"):
                month = int(groups["month_num"])
            else:
                month = _MONTH_NAME_TO_NUM[groups["month"].lower().rstrip(".")]
            return date(year, month, day), "absolute"
        except (KeyError, TypeError, ValueError):
            continue

    # 2. Relative dates anchored on the publish date, never on "now".
    if publish_date is not None:
        base = publish_date.date() if isinstance(publish_date, datetime) else publish_date
        for phrase, delta in _RELATIVE.items():
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                return base + timedelta(days=delta), "relative"
    else:
        for phrase in _RELATIVE:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                return None, "relative"  # cannot resolve without publish date

    # 3. Quarters resolve to the quarter end.
    m = _QUARTER_RE.search(snippet)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
        month = q * 3
        day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
        return date(year, month, day), "quarter"

    return None, "unknown"


def extract_direction(text: str) -> str | None:
    """Classify a policy/price change direction from its verbs."""
    if _HOLD.search(text):
        return "hold"
    raises = len(_RAISE.findall(text))
    cuts = len(_CUT.findall(text))
    if raises > cuts:
        return "raise"
    if cuts > raises:
        return "cut"
    if raises and cuts:
        return "mixed"
    return None


_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:percent|per cent|%)", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?:₦|N|\bNGN\b|\bUSD\b|\$|£|€)\s?[\d,]+(?:\.\d+)?(?:\s?(?:trillion|billion|million|bn|mn|m|k))?",
    re.IGNORECASE,
)


def extract_values(text: str) -> list[dict]:
    """Extract numeric values (money and percentages) with their offsets.

    Values are kept verbatim alongside the parsed number; missing units are
    never inferred here (the money parser owns that rule).
    """
    out: list[dict] = []
    for m in _PERCENT_RE.finditer(text):
        out.append(
            {
                "kind": "percent",
                "text": m.group(0),
                "value": float(m.group(1)),
                "unit": "percent",
                "start": m.start(),
                "end": m.end(),
            }
        )
    for m in _MONEY_RE.finditer(text):
        out.append(
            {
                "kind": "money",
                "text": m.group(0),
                "value": None,  # parsed separately by preprocessing.naira
                "unit": None,
                "start": m.start(),
                "end": m.end(),
            }
        )
    out.sort(key=lambda v: v["start"])
    return out


def actor_roles(
    entities: list[EntityPrediction], text: str, span: tuple[int, int] | None = None
) -> dict[str, list[str]]:
    """Very small subject/object tagging.

    We do not pretend to do semantic role labelling. This records which
    entities appear before the first trigger verb (likely actors) and which
    appear after (likely objects/targets), and says so in the key names.
    """
    snippet = text if span is None else text[span[0] : span[1]]
    offset = 0 if span is None else span[0]
    verb = re.search(
        r"\b(raised|cut|approved|fined|acquired|declared|announced|posted|"
        r"reported|suspended|revoked|paid|issued)\b",
        snippet,
        re.IGNORECASE,
    )
    pivot = offset + verb.start() if verb else len(text) // 2
    before: list[str] = []
    after: list[str] = []
    for e in entities:
        if span is not None and (e.span.end <= span[0] or e.span.start >= span[1]):
            continue  # entity lies entirely outside the analysed span
        name = e.canonical_name or e.span.text
        (before if e.span.start < pivot else after).append(name)
    return {"likely_subject": before, "likely_object": after}


def extract_attributes(
    text: str,
    *,
    publish_date: date | datetime | None = None,
    span: tuple[int, int] | None = None,
    entities: list[EntityPrediction] | None = None,
) -> ExtractedAttributes:
    """One call that collects every attribute for an event mention."""
    event_date, basis = extract_event_date(text, publish_date=publish_date, span=span)
    pub = (
        publish_date.date()
        if isinstance(publish_date, datetime)
        else publish_date
    )
    snippet = text if span is None else text[span[0] : span[1]]
    return ExtractedAttributes(
        event_date=event_date,
        publish_date=pub,
        date_basis=basis,
        direction=extract_direction(snippet),
        values=extract_values(snippet),
        actor_roles=actor_roles(entities or [], text, span),
    )


__all__ = [
    "ExtractedAttributes",
    "extract_attributes",
    "extract_direction",
    "extract_event_date",
    "extract_values",
    "actor_roles",
]
