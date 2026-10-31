"""Corporate-actions calendar endpoint: dividend schedules from event data.

The calendar is built from ``dividend`` events whose ``attributes`` carry a
merged schedule (qualification/payment dates, per-share amount) extracted by
``event_extraction.corporate_actions``. Honesty rules baked into the response:

* an entry only claims a date the text actually stated (``*_basis`` records
  how it was derived); ``date_known: false`` entries sort last and are never
  dropped silently;
* the event date is never conflated with the publish date — both are kept —
  and relative-schedule dates resolved against a publish date say so;
* every response carries the standing ``limitations[]`` tuple machine-readably
  (same contract as /analyze) and a verification note: extracted schedules
  are UNVERIFIED, readers confirm with the company's filing.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._common import get_db
from app.db import repositories
from naijafinsent.event_extraction.corporate_actions import schedule_dates
from naijafinsent.inference.pipeline import LIMITATIONS

router = APIRouter()

_CALENDAR_NOTE = (
    "UNVERIFIED UPSTREAM: dividend schedules are extracted from published "
    "text; qualification/payment dates and amounts can be revised by the "
    "company. Confirm against the company's filing. Not investment advice."
)


def _iso_or_none(value: Any) -> str | None:
    """ISO string for a date or an already-serialised date string; else None."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def _organisation(event: dict[str, Any]) -> str | None:
    """First ORG/TICKER-ish resolved entity name, else the headline."""
    for e in event.get("entities_json") or []:
        if not isinstance(e, dict):
            continue
        etype = str(e.get("type", "")).upper()
        if etype in {"ORG", "TICKER", "REGULATOR"}:
            name = e.get("canonical_name") or e.get("span", {}).get("text")
            if name:
                return str(name)
    return None


def _target_date(entry: dict[str, Any]) -> date | None:
    """The date the calendar sorts by: payment, event, qualification.

    Values may arrive as ``date`` objects or pre-serialised ISO strings
    (repository rows already carry ISO strings for date columns).
    """
    for key in ("payment_date", "event_date", "qualification_date"):
        value = entry.get(key)
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value)
            except ValueError:
                continue
    return None


@router.get("/")
def dividend_calendar(
    db: Session = Depends(get_db),
    event_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Corporate-actions calendar built from dividend events.

    ``event_id`` scopes the response to one event (deep-links / detail fetch).
    """
    repo = repositories.Repositories(db)
    rows, total = repo.events.list_events(event_type="dividend", limit=500)
    if event_id is not None:
        rows = [r for r in rows if r["id"] == event_id]
        total = len(rows)

    entries: list[dict[str, Any]] = []
    for row in rows:
        attrs = row.get("attributes") or {}
        qualification, payment = schedule_dates(attrs)
        amount = attrs.get("dividend_amount") if isinstance(attrs.get("dividend_amount"), dict) else None
        event_date = row.get("event_date")
        entry: dict[str, Any] = {
            "event_id": row["id"],
            "event_type": row.get("event_type"),
            "organisation": _organisation(row),
            "title": row.get("title"),
            "amount": amount,
            # A schedule entry is "known" only when the text stated a date.
            "date_known": any(
                d is not None
                for d in (event_date, payment, qualification)
            ),
            "qualification_date": qualification.isoformat() if qualification else None,
            "qualification_basis": attrs.get("qualification_basis"),
            "payment_date": payment.isoformat() if payment else None,
            "payment_basis": attrs.get("payment_basis"),
            "event_date": event_date.isoformat()
            if isinstance(event_date, date)
            else (event_date if isinstance(event_date, str) else None),
            # Publish date is deliberately separate: it is when coverage
            # appeared, never when the corporate action happens.
            "publish_date": _iso_or_none(row.get("publish_date")),
            "clusters": {"cluster_id": row.get("cluster_id"), "is_primary": row.get("is_primary")},
        }
        entries.append(entry)

    # Calendar filter: the *schedule* window (payment/event/qualification),
    # not the publish window. Entries without any stated date never match a
    # range and would vanish silently — they are returned under
    # "undated_count" instead.
    windowed = [
        e for e in entries
        if (_d := _target_date(e)) is not None
        and (date_from is None or _d >= date_from)
        and (date_to is None or _d <= date_to)
    ]
    undated = [e for e in entries if _target_date(e) is None]
    if date_from is not None or date_to is not None:
        shown = windowed
    else:
        shown = windowed + undated
    shown.sort(key=lambda e: (_target_date(e) is None, _target_date(e) or date.max, e["event_id"]))

    page = shown[offset : offset + limit]
    return {
        "calendar": page,
        "count": len(page),
        "total": len(shown),
        "undated_count": len(undated),
        "verification_note": _CALENDAR_NOTE,
        "limitations": list(LIMITATIONS),
    }
