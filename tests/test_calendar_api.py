"""API tests for the dividend corporate-actions calendar (``/api/v1/calendar``).

Seeds ``dividend`` FinancialEvent rows (with merged schedule attributes, the
shape the pipeline produces) into the app's own database, then checks the
http surface. Every assertion filters by the seeded ``event_id`` so the
tests stay exact even when they share a database with other integration
suites. Checks: entry shape, honest date handling, machine-readable
limitations, and the UNVERIFIED verification note.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Throwaway DB *before* the app (and its engine) is imported.
_TMP = tempfile.mkdtemp(prefix="naijafinsent-calendar-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"

API_DIR = Path(__file__).resolve().parents[1] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402

from app.db import models as db_models  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from naijafinsent.inference.pipeline import LIMITATIONS  # noqa: E402

client = TestClient(app)


def _seed_dividend(**overrides):
    session = SessionLocal()
    try:
        row = db_models.FinancialEvent(
            event_type="dividend",
            event_date=overrides.pop("event_date", date(2026, 3, 26)),
            publish_date=overrides.pop("publish_date", date(2026, 3, 10)),
            title=overrides.pop("title", "MTN Nigeria declares interim dividend"),
            attributes=overrides.pop(
                "attributes",
                {
                    "direction": None,
                    "values": [],
                    "qualification_date": "2026-04-15",
                    "qualification_basis": "absolute",
                    "payment_date": "2026-05-27",
                    "payment_basis": "absolute",
                    "dividend_amount": {
                        "text": "6 kobo per share",
                        "per_share_value": 6.0,
                        "unit": "kobo",
                        "stated_per_share": True,
                    },
                },
            ),
            entities_json=overrides.pop(
                "entities_json",
                [{"type": "ORG", "canonical_name": "MTN Nigeria Communications Plc",
                  "span": {"text": "MTN Nigeria", "start": 0, "end": 11}}],
            ),
            is_primary=True,
        )
        session.add(row)
        session.commit()
        return row.id
    finally:
        session.close()


# Seeds run in a module-scoped fixture (NOT at import): pytest imports all
# test modules during collection, and import-time seeding would pollute the
# envelope tests of test_api_endpoints, which assume an empty database.
_ID_A = _ID_B = _ID_UNDATED = None


@pytest.fixture(scope="module", autouse=True)
def _seeded_ids():
    global _ID_A, _ID_B, _ID_UNDATED
    _ID_A = _seed_dividend()  # payment 2026-05-27
    _ID_B = _seed_dividend(
        title="Zenith Bank final dividend",
        attributes={
            "payment_date": "2026-04-10",
            "payment_basis": "absolute",
            "qualification_date": "2026-04-08",
            "qualification_basis": "absolute",
            "dividend_amount": {
                "text": "N1.85 per share",
                "per_share_value": 1.85,
                "unit": "naira",
                "stated_per_share": True,
            },
        },
        event_date=date(2026, 4, 10),
    )
    _ID_UNDATED = _seed_dividend(
        event_date=None,
        title="Undated dividend story",
        attributes={"payment_date": None, "payment_basis": "relative-unresolved"},
    )


def _calendar(params=None):
    return client.get("/api/v1/calendar", params=params).json()


def test_calendar_envelope_and_entry_shape():
    body = _calendar({"event_id": _ID_A})
    assert set(body) >= {"calendar", "count", "total", "undated_count",
                         "verification_note", "limitations"}
    assert body["total"] == 1
    entry = body["calendar"][0]
    assert entry["event_id"] == _ID_A
    required = {
        "event_id", "event_type", "organisation", "title", "amount",
        "date_known", "qualification_date", "qualification_basis",
        "payment_date", "payment_basis", "event_date", "publish_date",
    }
    assert required <= set(entry)


def test_calendar_sorted_by_schedule_date_not_publish_date():
    body = _calendar()
    mine = [e for e in body["calendar"] if e["event_id"] in {_ID_A, _ID_B}]
    assert len(mine) == 2
    first, second = mine if mine[0]["event_id"] == _ID_B else mine[::-1]
    # Sorted by the SCHEDULE date (payment), not by publish/event dates.
    assert first["payment_date"] == "2026-04-10"
    assert second["payment_date"] == "2026-05-27"


def test_organisation_comes_from_resolved_entity_not_title():
    body = _calendar({"event_id": _ID_A})
    assert body["calendar"][0]["organisation"] == "MTN Nigeria Communications Plc"


def test_amount_carries_stated_unit_and_value():
    assert _calendar({"event_id": _ID_A})["calendar"][0]["amount"]["unit"] == "kobo"
    b = _calendar({"event_id": _ID_B})["calendar"][0]["amount"]
    assert b["unit"] == "naira"
    assert b["per_share_value"] == 1.85


def test_date_window_filters_on_schedule_not_publish():
    # Publish date of entry A is 2026-03-10; its payment is 2026-05-27. A
    # publish-date window would wrongly include it; the schedule window here
    # must include it via payment, and must NOT match B.
    body = _calendar({
        "event_id": _ID_A,
        "date_from": "2026-05-01", "date_to": "2026-05-31",
    })
    assert body["total"] == 1 and body["calendar"][0]["event_id"] == _ID_A
    excluded = _calendar({
        "event_id": _ID_B,
        "date_from": "2026-05-01", "date_to": "2026-05-31",
    })
    assert excluded["total"] == 0


def test_undated_entries_are_visible_but_naive_windows_never_claim_them():
    undated = _calendar({"event_id": _ID_UNDATED})
    assert undated["total"] == 1
    entry = undated["calendar"][0]
    assert entry["date_known"] is False
    assert entry["payment_date"] is None
    # With a window, the undated entry is excluded (never silently dated).
    windowed = _calendar({
        "event_id": _ID_UNDATED,
        "date_from": "2026-01-01", "date_to": "2026-12-31",
    })
    assert windowed["total"] == 0


def test_limitations_and_verification_note_machine_readable():
    body = _calendar({"event_id": _ID_A})
    assert body["limitations"] == list(LIMITATIONS)
    assert "UNVERIFIED" in body["verification_note"]
    assert "Not investment advice" in body["verification_note"]
    # Publish/event separation is visible per entry (never merged).
    entry = body["calendar"][0]
    assert entry["publish_date"] is not None
