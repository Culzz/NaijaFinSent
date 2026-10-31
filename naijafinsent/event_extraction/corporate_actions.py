"""Corporate-action schedule extraction (dividends first).

The calendar product needs the three dates a dividend story actually reports
— declaration/announcement (often the publish date), the *qualification*
("qualifying date" / "closure of register") and the *payment* date. Extraction
rules are deliberately narrow and honest:

* a schedule date is only extracted when an **absolute** date sits in the
  same short window as the phrase (or a relative phrase exists AND a publish
  date is supplied; relative-to-publish works exactly like
  ``attributes.extract_event_date``). With no publish date and no absolute
  date, the field stays ``None`` with basis ``relative-unresolved`` — it is
  **never guessed** from "now";
* the dividend amount is only extracted when the story states it **per
  share** (the Nigerian-reporting convention: "interim dividend of 6 kobo
  per share"), and only when the currency is *stated* (₦/N/NGN → naira, the
  word ``kobo`` → kobo). A missing currency is never inferred — this mirrors
  the money-parser rule in ``preprocessing.naira``.

All returned dates are ISO strings so the dicts can go straight into the
JSON ``attributes`` column; ``date`` conversions happen at the caller.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from naijafinsent.event_extraction.attributes import (
    _DATE_PATTERNS,
    _MONTH_NAME_TO_NUM,
)

# "qualifying date", "qualification date", "closure of register", "register closes"
_QUALIFY_RE = re.compile(
    r"(?:quali(?:fying|fication)\s+date|qualification\s+period|"
    r"closure\s+of\s+(?:its?\s+)?register|register\s+(?:shall\s+)?close)",
    re.IGNORECASE,
)
# "payment date", "payable on/from ...", "will be paid on ..."
_PAYMENT_RE = re.compile(
    r"(?:payment\s+(?:will\s+)?(?:be\s+)?(?:made\s+on|date)|payout\s+date|"
    r"payable(?:\s+on|\s+from)?|will\s+be\s+paid\s+on|shall\s+be\s+paid\s+on)",
    re.IGNORECASE,
)
# Relative phrases that may appear in a schedule window.
_RELATIVE_PHRASES = {
    "tomorrow": 1,
    "today": 0,
    "yesterday": -1,
    "next week": 7,
    "next month": 30,
}

# Per-share dividend amount: currency must be stated. "kobo" before "kobo per
# share" alternation so both endings match; the naira branch requires the ₦/N/
# NGN marker (that is what disambiguates "N1.85 per share" from a bare 1.85).
_PER_SHARE_RE = re.compile(
    r"(?:(?:₦|N(?:GN)?)\s?(?P<naira>[\d,]{1,7}(?:\.\d+)?)\s*(?:kobo)?"
    r"|(?P<kobo>[\d,]{1,7}(?:\.\d+)?)\s+kobo)"
    r"(?:\s*per\s+share)?",
    re.IGNORECASE,
)

_WINDOW = 50  # characters searched after a schedule phrase for a date


def _to_date(groups: dict[str, str | None]) -> date | None:
    """One parsed date from an attributes._DATE_PATTERNS match."""
    try:
        year = int(groups["year"])  # type: ignore[arg-type]
        day = int(groups["day"])  # type: ignore[arg-type]
        if groups.get("month_num"):
            month = int(groups["month_num"])
        else:
            month = _MONTH_NAME_TO_NUM[groups["month"].lower().rstrip(".")]
        return date(year, month, day)
    except (KeyError, TypeError, ValueError):
        return None


def _window_date(window: str, publish_date: date | datetime | None) -> tuple[date | None, str]:
    """First resolvable date inside a short window, with an honest basis."""
    for pattern in _DATE_PATTERNS:
        m = pattern.search(window)
        if m:
            parsed = _to_date(m.groupdict())
            if parsed is not None:
                return parsed, "absolute"
    lowered = window.lower()
    for phrase, delta in _RELATIVE_PHRASES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            if publish_date is None:
                return None, "relative-unresolved"
            base = publish_date.date() if isinstance(publish_date, datetime) else publish_date
            return base + timedelta(days=delta), "relative"
    return None, "not-stated"


def _first_amount(snippet: str) -> dict | None:
    """The per-share dividend amount, when the text states one with a currency."""
    best: dict | None = None
    for m in _PER_SHARE_RE.finditer(snippet):
        tail = snippet[m.end() : m.end() + 40]
        per_share = "per share" in m.group(0).lower() or "per share" in tail.lower()
        if m.group("kobo") is not None:
            unit = "kobo"
            raw = m.group("kobo")
        elif m.group("naira") is not None:
            # "N25 kobo" states kobo; a kobo word anywhere in the match wins.
            unit = "kobo" if m.group(0).lower().find("kobo") != -1 else "naira"
            raw = m.group("naira")
        else:  # pragma: no cover - the alternation always binds one branch
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - regex guarantees digits
            continue
        cand = {
            "text": m.group(0).strip(),
            "per_share_value": value,
            "unit": unit,
            "stated_per_share": per_share,
        }
        # Prefer an explicit per-share statement; otherwise the first amount.
        if best is None or (per_share and not best.get("stated_per_share")):
            best = cand
    return best


def extract_dividend_schedule(
    text: str,
    *,
    publish_date: date | datetime | None = None,
    span: tuple[int, int] | None = None,
) -> dict:
    """Extract qualification/payment dates and the per-share dividend amount.

    Returns a dict whose keys are honestly ``None`` when the text does not
    state them; nothing is inferred from context, newspaper conventions, or
    "now". Dates are ISO strings (JSON-safe); the caller converts to ``date``
    where it needs a typed value.
    """
    snippet = text if span is None else text[span[0] : span[1]]

    qualify_date, qualify_basis = (None, "not-stated")
    m = _QUALIFY_RE.search(snippet)
    if m:
        qualify_date, qualify_basis = _window_date(snippet[m.end() : m.end() + _WINDOW], publish_date)

    pay_date, pay_basis = (None, "not-stated")
    m = _PAYMENT_RE.search(snippet)
    if m:
        pay_date, pay_basis = _window_date(snippet[m.end() : m.end() + _WINDOW], publish_date)

    out: dict = {
        "qualification_date": qualify_date.isoformat() if qualify_date else None,
        "qualification_basis": qualify_basis,
        "payment_date": pay_date.isoformat() if pay_date else None,
        "payment_basis": pay_basis,
    }
    amount = _first_amount(snippet)
    if amount is not None:
        out["dividend_amount"] = amount
    return out


def schedule_dates(event_attributes: dict) -> tuple[date | None, date | None]:
    """Typed view for the API layer: ``(qualification_date, payment_date)``.

    Accepts the merged ``attributes`` dict from an event and parses the ISO
    strings back into ``date`` objects, tolerating absent keys.
    """
    qual = pay = None
    raw_q = event_attributes.get("qualification_date")
    raw_p = event_attributes.get("payment_date")
    if isinstance(raw_q, str) and raw_q:
        try:
            qual = date.fromisoformat(raw_q)
        except ValueError:
            qual = None
    if isinstance(raw_p, str) and raw_p:
        try:
            pay = date.fromisoformat(raw_p)
        except ValueError:
            pay = None
    return qual, pay


__all__ = ["extract_dividend_schedule", "schedule_dates"]
