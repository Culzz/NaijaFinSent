"""Naira / foreign-currency money mention parsing.

Two jobs:

1. ``parse_money(span_text) -> dict`` -- normalise a single money surface form
   into ``{"value", "currency", "unit"}``. The cardinal rule from
   ``schemas.MoneyAnnotation`` is respected: **never infer a missing unit**.
   ``"N2"`` yields ``unit=None``; ``"N2bn"`` yields ``unit="billion"``.

2. ``find_money_mentions(text) -> list[EntitySpan]`` -- locate money spans in a
   document with regexes, returning ``EntitySpan`` objects typed ``MONEY``.

The parser is deliberately conservative: it prefers ``unit=None`` over guessing,
and it disambiguates ``"$40 oil"`` (unit=None, a price) from ``"$40m"``
(unit="million", an amount).
"""

from __future__ import annotations

import re
from typing import TypedDict

from naijafinsent.schemas import EntitySpan, EntityType

__all__ = [
    "MoneyParse",
    "parse_money",
    "find_money_mentions",
    "normalise_unit",
    "CURRENCY_SYMBOLS",
]


class MoneyParse(TypedDict):
    """Structural type for :func:`parse_money` output.

    Matches ``MoneyAnnotation`` fields ``value``/``currency``/``unit`` so callers
    can build a ``MoneyAnnotation`` from it directly.
    """

    value: float | None
    currency: str | None
    unit: str | None


# --- Currency detection -------------------------------------------------------
# Symbol / word -> ISO 4217 code.
CURRENCY_SYMBOLS: dict[str, str] = {
    "\u20a6": "NGN",   # ₦
    "$": "USD",
    "\u00a3": "GBP",   # £
    "\u20ac": "EUR",   # €
}

_CURRENCY_WORDS: dict[str, str] = {
    "naira": "NGN",
    "kobo": "NGN",
    "ngn": "NGN",
    "\u20a6": "NGN",
    "dollar": "USD",
    "dollars": "USD",
    "usd": "USD",
    "pound": "GBP",
    "pounds": "GBP",
    "gbp": "GBP",
    "sterling": "GBP",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "cent": "USD",
    "cents": "USD",
}

# --- Unit mapping -------------------------------------------------------------
_UNIT_WORDS: dict[str, str] = {
    "trillion": "trillion",
    "trn": "trillion",
    "tn": "trillion",
    "t": "trillion",
    "billion": "billion",
    "bn": "billion",
    "b": "billion",
    "million": "million",
    "mn": "million",
    "m": "million",
    "thousand": "thousand",
    "k": "thousand",
}

_MULTIPLIERS: dict[str, float] = {
    "trillion": 1e12,
    "billion": 1e9,
    "million": 1e6,
    "thousand": 1e3,
}


def normalise_unit(token: str | None) -> str | None:
    """Map a unit surface form to a canonical unit or ``None``."""
    if token is None:
        return None
    key = token.strip().lower().rstrip(".")
    return _UNIT_WORDS.get(key)


# --- Surface-form regex -------------------------------------------------------
# A number: 1,234.5 | 1.5 | 1234
_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\d*\.\d+"

# Currency prefix: ₦ N NGN naira $ USD £ GBP € EUR (word-boundary aware for N).
_CURRENCY_PREFIX = (
    r"(?:\u20a6|\$|\u00a3|\u20ac|NGN|USD|GBP|EUR|naira|N(?=\d))"
)

def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _detect_currency(text: str) -> str | None:
    """Detect the ISO currency code from a money surface form."""
    stripped = text.strip()
    if not stripped:
        return None
    # Symbol / code at the very start.
    for sym, iso in CURRENCY_SYMBOLS.items():
        if stripped.startswith(sym):
            return iso
    head = re.match(r"[A-Za-z]+", stripped)
    if head:
        word = head.group(0).lower()
        if word in _CURRENCY_WORDS:
            return _CURRENCY_WORDS[word]
    # A bare "N" immediately before a digit means naira.
    if re.match(r"N\d", stripped):
        return "NGN"
    # Currency word anywhere (e.g. "40 million naira").
    for word, iso in _CURRENCY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", stripped, re.IGNORECASE):
            return iso
    return None


def _extract_number_and_unit(text: str) -> tuple[float | None, str | None, float | None]:
    """Return ``(value_for_midpoint, unit, high_value)``.

    For a range we return the midpoint as ``value`` and the upper bound as the
    third element (callers that only need ``value`` use the midpoint).
    """
    # Strip a leading currency marker / word so only "number [unit]" remains.
    body = text.strip()
    body = re.sub(r"^(?:\u20a6|\$|\u00a3|\u20ac|NGN|USD|GBP|EUR|naira)\s*", "", body,
                  flags=re.IGNORECASE)
    if re.match(r"N\d", body):
        body = body[1:]

    m = re.search(
        rf"(?P<num>{_NUMBER})"
        rf"(?:\s*(?:-|\u2013|\u2014|to)\s*(?P<num2>{_NUMBER}))?"
        rf"\s*(?P<unit>trillion|trn|tn|billion|bn|million|mn|thousand|k|b|m|t)?\b",
        body,
        re.IGNORECASE,
    )
    if not m:
        return None, None, None

    lo = _to_float(m.group("num"))
    hi = _to_float(m.group("num2")) if m.group("num2") else None
    unit = normalise_unit(m.group("unit"))

    if lo is None:
        return None, unit, hi

    if hi is not None:
        value = (lo + hi) / 2.0
    else:
        value = lo

    # Scale to absolute units when a unit is present (e.g. 2 bn -> 2e9).
    if unit in _MULTIPLIERS:
        mult = _MULTIPLIERS[unit]
        value *= mult
        if hi is not None:
            hi *= mult
    return value, unit, hi


def parse_money(span_text: str) -> MoneyParse:
    """Parse a money surface form into ``{"value", "currency", "unit"}``.

    Rules:

    * Currency is detected from symbol (``₦``/``$``/``£``/``€``), code
      (``NGN``/``USD``/...), a bare ``N`` directly before digits, or a currency
      word (``naira``/``kobo``/``dollar``...). Absent any signal -> ``None``.
    * Unit is taken **only** if explicitly written as a word or abbreviation
      that denotes a scale (``bn``/``billion``/``m``/``million``/``k``...).
      ``"N2"`` therefore returns ``unit=None`` -- never inferred.
    * ``value`` is the numeric magnitude scaled by the unit multiplier
      (e.g. ``"₦2.3bn"`` -> ``2.3e9``). Ranges return the midpoint.
    * ``"$40 oil"`` -> ``unit=None`` (``oil`` is not a unit); ``"$40m"`` ->
      ``unit="million"``.

    Examples:
        >>> parse_money("₦2.3bn")
        {'value': 2300000000.0, 'currency': 'NGN', 'unit': 'billion'}
        >>> parse_money("N2")
        {'value': 2.0, 'currency': 'NGN', 'unit': None}
        >>> parse_money("$40 oil")["unit"] is None
        True
    """
    text = (span_text or "").strip()
    if not text:
        return MoneyParse(value=None, currency=None, unit=None)

    currency = _detect_currency(text)
    value, unit, _hi = _extract_number_and_unit(text)
    return MoneyParse(value=value, currency=currency, unit=unit)


# --------------------------------------------------------------------------
# Document-level extraction
# --------------------------------------------------------------------------

# A standalone money span for search: currency marker required OR a
# number+unit with a currency word nearby. We require an explicit currency
# marker/word to avoid matching every bare number in an article.
_MONEY_SPAN_RE = re.compile(
    rf"""
    (?:
        (?P<sym>\u20a6|\$|\u00a3|\u20ac)                       # symbol prefix
        \s*(?P<num1>{_NUMBER})?
        (?:\s*(?:-|\u2013|\u2014|to)\s*(?P<num1b>{_NUMBER}))?
        \s*(?P<unit1>trillion|trn|tn|billion|bn|million|mn|thousand|k|b|m|t)?\b
    )
    |
    (?:
        (?P<code>NGN|USD|GBP|EUR)                             # ISO code
        \s*(?P<num2>{_NUMBER})?
        (?:\s*(?:-|\u2013|\u2014|to)\s*(?P<num2b>{_NUMBER}))?
        \s*(?P<unit2>trillion|trn|tn|billion|bn|million|mn|thousand|k|b|m|t)?\b
    )
    |
    (?:
        (?P<nmark>N)(?P<num3>{_NUMBER})                        # bare N + digits
        (?:\s*(?:-|\u2013|\u2014|to)\s*(?P<num3b>{_NUMBER}))?
        \s*(?P<unit3>trillion|trn|tn|billion|bn|million|mn|thousand|kobo|k)?\b
    )
    |
    (?:
        (?P<num4>{_NUMBER})                                    # number + scale + word
        \s*(?P<unit4>trillion|billion|million|thousand)\s*
        (?P<word4>naira|kobo|dollars?|pounds?|euros?)
        \b
    )
    |
    (?:
        (?P<num5>{_NUMBER})                                    # bare scaled amount (1.2trn)
        \s*(?P<unit5>trillion|trn|tn|billion|bn|million)\b
        (?!\s*(?:barrels?|bpd|per\b|basis\b))
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def find_money_mentions(text: str) -> list[EntitySpan]:
    """Find money mentions in ``text`` and return them as ``EntitySpan`` objects.

    Deterministic, regex-based, and non-overlapping (leftmost-longest). Requires
    either an explicit currency marker (symbol, ISO code, bare ``N`` before
    digits, or a currency word directly after a scale word) **or** an explicit
    scale word (``1.2trn``, ``450bn``) — a bare scaled amount carries no
    inferred currency and any consumer must read its ``currency: None``
    honestly. Scaled amounts immediately followed by oil/unit nouns
    (``1.2 million barrels``, ``per basis``) are not money; we tag arbitrary
    numbers never. Spans are typed ``EntityType.MONEY`` with offsets into
    ``text``.
    """
    if not text:
        return []

    spans: list[EntitySpan] = []
    last_end = -1
    for m in _MONEY_SPAN_RE.finditer(text):
        start, end = m.start(), m.end()
        # Trim trailing whitespace captured by the optional-unit group.
        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start or start < last_end:
            continue
        surface = text[start:end]
        # Sanity: must contain a digit.
        if not any(ch.isdigit() for ch in surface):
            continue
        spans.append(
            EntitySpan(
                start=start,
                end=end,
                text=surface,
                entity_type=EntityType.MONEY,
            )
        )
        last_end = end
    return spans
