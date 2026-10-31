"""Core tests for dividend-schedule extraction (corporate_actions).

The rule under test everywhere: a schedule date is only returned when the
text *states* it — absolutely, or relatively WITH a publish date. Missing
currency is never inferred for the per-share amount.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from naijafinsent.event_extraction.corporate_actions import (  # noqa: E402
    extract_dividend_schedule,
    schedule_dates,
)


def test_full_schedule_absolute_dates():
    text = (
        "MTN Nigeria declared an interim dividend of 6 kobo per share with "
        "the closure of register on 15 April 2026 and payment will be made "
        "on 27 May 2026."
    )
    s = extract_dividend_schedule(text)
    assert s["qualification_date"] == "2026-04-15"
    assert s["qualification_basis"] == "absolute"
    assert s["payment_date"] == "2026-05-27"
    assert s["payment_basis"] == "absolute"
    assert s["dividend_amount"]["per_share_value"] == 6.0
    assert s["dividend_amount"]["unit"] == "kobo"
    assert s["dividend_amount"]["stated_per_share"] is True


def test_day_first_dashed_date():
    text = "A dividend of 12 kobo per share, qualifying date 19-04-2026."
    s = extract_dividend_schedule(text)
    assert s["qualification_date"] == "2026-04-19"
    assert s["dividend_amount"]["text"] == "12 kobo per share"


def test_relative_payment_resolves_only_with_publish_date():
    text = "The bank announced a dividend of N1.85 per share, payable from next week."
    without = extract_dividend_schedule(text)
    assert without["payment_date"] is None
    assert without["payment_basis"] == "relative-unresolved"

    with_pub = extract_dividend_schedule(text, publish_date=date(2026, 3, 1))
    assert with_pub["payment_date"] == "2026-03-08"
    assert with_pub["payment_basis"] == "relative"


def test_relative_with_publish_date_and_amount_unit_is_naira():
    text = "Zenith Bank declared a dividend of N2.50 per share payable from tomorrow."
    s = extract_dividend_schedule(text, publish_date=date(2026, 3, 1))
    assert s["payment_date"] == "2026-03-02"
    assert s["dividend_amount"]["unit"] == "naira"
    assert s["dividend_amount"]["per_share_value"] == 2.50


def test_no_currency_never_infers_amount():
    text = "The board proposed an interim dividend of 6 per share, payment date 27 May 2026."
    s = extract_dividend_schedule(text)
    assert "dividend_amount" not in s  # currency not stated -> no amount claimed
    assert s["payment_date"] == "2026-05-27"


def test_nothing_stated_returns_clean_nones():
    text = "The company reported profit after tax of 12 percent for Q1 2026."
    s = extract_dividend_schedule(text)
    assert s == {
        "qualification_date": None,
        "qualification_basis": "not-stated",
        "payment_date": None,
        "payment_basis": "not-stated",
    }


def test_schedule_dates_typed_view_round_trip():
    s = extract_dividend_schedule(
        "dividend of 6 kobo per share; qualifying date 15 April 2026; "
        "payment date 27 May 2026."
    )
    qual, pay = schedule_dates(s)
    assert qual == date(2026, 4, 15)
    assert pay == date(2026, 5, 27)
    # Absent/malformed keys must not raise.
    assert schedule_dates({}) == (None, None)
    assert schedule_dates({"qualification_date": "not-a-date", "payment_date": None}) == (None, None)
