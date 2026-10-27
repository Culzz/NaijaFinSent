"""Tests for attribute extraction: dates, directions, values, actor roles.

The event date is deliberately NOT the publish date — tests pin the two-clock
behaviour because conflating them is the classic event-study error.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from naijafinsent.event_extraction.attributes import (
    ExtractedAttributes,
    actor_roles,
    extract_attributes,
    extract_direction,
    extract_event_date,
    extract_values,
)


# ---------------------------------------------------------------------------
# Dates: absolute / relative / quarter / unknown, with the publish-date anchor
# ---------------------------------------------------------------------------

def test_absolute_dates_parse_all_calendar_orderings():
    cases = {
        "The CBN met on 24 October 2026 and raised the rate.": date(2026, 10, 24),
        "Results were released on 24 Oct 2026.": date(2026, 10, 24),
        "The bank posted results on October 24, 2026.": date(2026, 10, 24),
        "Rate decision announced on 2026-10-24.": date(2026, 10, 24),
    }
    for text, expected in cases.items():
        event_date, basis = extract_event_date(text)
        assert event_date == expected, text
        assert basis == "absolute"


def test_relative_dates_anchor_on_publish_date_never_now():
    text = "The bank will hold its results review next week."
    with_publish, basis = extract_event_date(text, publish_date=date(2026, 10, 20))
    assert basis == "relative"
    assert with_publish == date(2026, 10, 27)  # anchored on publish date, +7d

    # Without a publish date a relative mention must NOT silently "resolve"
    # to today: it is returned unresolved.
    event_date, basis = extract_event_date(text)
    assert event_date is None
    assert basis == "relative"


def test_same_relative_text_two_publish_dates_two_event_dates():
    """Same words, different publish dates -> different event dates."""
    text = "Results are due next week."
    d1, _ = extract_event_date(text, publish_date=date(2026, 3, 1))
    d2, _ = extract_event_date(text, publish_date=date(2026, 9, 10))
    assert d1 != d2


def test_quarter_resolves_to_quarter_end():
    event_date, basis = extract_event_date("The board approved the results for Q3 2026.")
    assert basis == "quarter"
    assert event_date == date(2026, 9, 30)


def test_unknown_text_yields_unknown_basis():
    event_date, basis = extract_event_date("Shares of the lender rallied at the open.")
    assert event_date is None
    assert basis == "unknown"


def test_absolute_wins_over_relative_in_the_same_text():
    text = "The CBN raised the rate on 24 October 2026, a week after market chatter."
    event_date, basis = extract_event_date(text, publish_date=date(2026, 10, 1))
    assert basis == "absolute"
    assert event_date == date(2026, 10, 24)


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The CBN raised the policy rate by 50 basis points.", "raise"),
        ("The committee cut the rate amid slowing growth.", "cut"),
        ("The MPC holds the rate at 27.50 percent.", "hold"),
        ("The bank raised its dividend but cut its outlook.", "mixed"),
        ("The bank posted results for the half year.", None),
    ],
)
def test_extract_direction(text, expected):
    assert extract_direction(text) == expected


# ---------------------------------------------------------------------------
# Values: percent parsed, money kept verbatim for the naira parser
# ---------------------------------------------------------------------------

def test_percent_values_are_parsed_with_offsets():
    text = "The committee retained the MPR at 27.5 percent."
    vals = extract_values(text)
    pct = [v for v in vals if v["kind"] == "percent"]
    assert len(pct) == 1
    v = pct[0]
    assert v["value"] == 27.5
    assert v["unit"] == "percent"
    # Offsets must slice the original string exactly.
    assert text[v["start"] : v["end"]] == v["text"]


def test_naira_and_foreign_currencies_are_captured_verbatim():
    for snippet in ("₦", "NGN"):
        text = f"declared a dividend of {snippet}25 billion"
        vals = [v for v in extract_values(text) if v["kind"] == "money"]
        assert len(vals) == 1, snippet
        # Money is deliberately NOT parsed here — preprocessing.naira owns it.
        assert vals[0]["value"] is None
        assert text[vals[0]["start"] : vals[0]["end"]] == vals[0]["text"]


def test_percent_and_money_are_sorted_by_position():
    text = "₦459 billion profit, up 34 percent year on year."
    vals = extract_values(text)
    assert [v["start"] for v in vals] == sorted(v["start"] for v in vals)
    assert {v["kind"] for v in vals} == {"money", "percent"}


def test_no_values_in_plain_text():
    assert extract_values("The bank posted results.") == []


# ---------------------------------------------------------------------------
# extract_attributes: the assembled record
# ---------------------------------------------------------------------------

def test_extract_attributes_shapes_the_full_record():
    text = "On 24 October 2026 the CBN raised the MPR by 50 basis points to 27.5 percent."
    attrs = extract_attributes(text, publish_date=datetime(2026, 10, 25, 9, 0))
    assert isinstance(attrs, ExtractedAttributes)
    # Event date comes from the text; publish date is recorded separately.
    assert attrs.event_date == date(2026, 10, 24)
    assert attrs.publish_date == date(2026, 10, 25)
    assert attrs.date_basis == "absolute"
    assert attrs.direction == "raise"
    kinds = {v["kind"] for v in attrs.values}
    # "50 basis points" is basis_points, "27.5 percent" is percent. There is no
    # money here — and, since the currency-regex fix, stray "n" + digits (as in
    # "On ... n 2026") no longer masquerade as naira amounts.
    assert kinds == {"basis_points", "percent"}


def test_extract_attributes_relative_needs_publish_date():
    without = extract_attributes("Results will be published next week.")
    assert without.date_basis == "relative"
    assert without.event_date is None

    with_publish = extract_attributes(
        "Results will be published next week.", publish_date=date(2026, 10, 1)
    )
    assert with_publish.event_date == date(2026, 10, 8)


# ---------------------------------------------------------------------------
# actor_roles
# ---------------------------------------------------------------------------

def test_actor_roles_are_positional_and_honest():
    from naijafinsent.schemas import EntityPrediction, EntitySpan

    text = "Zenith Bank raised its target after the CBN approved the licence."
    entities = [
        EntityPrediction(
            span=EntitySpan(start=0, end=11, text="Zenith Bank", entity_type="ORG"),
            canonical_name="Zenith Bank",
        ),
        EntityPrediction(
            span=EntitySpan(start=33, end=36, text="the", entity_type="ORG"),
            canonical_name="CBN",
        ),
    ]
    roles = actor_roles(entities, text)
    # Positional key names — we do NOT pretend this is semantic role labelling.
    assert roles["likely_subject"] == ["Zenith Bank"]
    assert "CBN" in roles["likely_object"]


def test_actor_roles_span_limits_reach():
    from naijafinsent.schemas import EntityPrediction, EntitySpan

    text = "Zenith Bank raised its outlook; the market shrugged."
    entities = [
        EntityPrediction(
            span=EntitySpan(start=0, end=11, text="Zenith Bank", entity_type="ORG"),
            canonical_name="Zenith Bank",
        ),
        EntityPrediction(
            span=EntitySpan(start=33, end=39, text="market", entity_type="ORG"),
            canonical_name="market",
        ),
    ]
    roles = actor_roles(entities, text, span=(0, len("Zenith Bank raised its outlook;")))
    combined = {name for names in roles.values() for name in names}
    assert "Zenith Bank" in combined
    assert "market" not in combined  # outside the span
