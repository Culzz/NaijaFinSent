"""Seed clearly-marked synthetic demo events into the live sqlite database.

Run manually from the repo root with the same DATABASE_URL as the live
server. Purpose: make the /calendar first look presentable; titles carry a
[SYNTHETIC DEMO] prefix so nobody mistakes fixture data for ingested facts.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./data/processed/live_api.db"
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "services/api")

from app.db import models as dbm
from app.db.base import SessionLocal

LOG = Path(".live/seed.log")
log = LOG.open("a", encoding="utf-8")


def note(msg: str) -> None:
    log.write(msg + "\n")
    log.flush()


rows = [
    dict(
        title="[SYNTHETIC DEMO] MTN Nigeria declares interim dividend of 6 kobo per share",
        attrs={
            "qualification_date": "2026-04-15", "qualification_basis": "absolute",
            "payment_date": "2026-05-27", "payment_basis": "absolute",
            "dividend_amount": {"text": "6 kobo per share", "per_share_value": 6.0,
                                "unit": "kobo", "stated_per_share": True},
        },
        event_date=date(2026, 5, 27), org="MTN Nigeria Communications Plc",
    ),
    dict(
        title="[SYNTHETIC DEMO] Zenith Bank proposes final dividend of N1.85 per share",
        attrs={
            "qualification_date": "2026-04-08", "qualification_basis": "absolute",
            "payment_date": "2026-04-10", "payment_basis": "absolute",
            "dividend_amount": {"text": "N1.85 per share", "per_share_value": 1.85,
                                "unit": "naira", "stated_per_share": True},
        },
        event_date=date(2026, 4, 10), org="Zenith Bank Plc",
    ),
    dict(
        title="[SYNTHETIC DEMO] Dangote Cement declares interim dividend of N15 per share; register closes 22 May",
        attrs={
            "qualification_date": "2026-05-22", "qualification_basis": "absolute",
            "payment_date": None, "payment_basis": "not-stated",
            "dividend_amount": {"text": "N15.00", "per_share_value": 15.0,
                                "unit": "naira", "stated_per_share": True},
        },
        event_date=date(2026, 5, 22), org="Dangote Cement Plc",
    ),
]

note("opening session")
s = SessionLocal()
note("session open, adding rows")
for r in rows:
    s.add(
        dbm.FinancialEvent(
            event_type="dividend",
            event_date=r["event_date"],
            publish_date=date(2026, 3, 10),
            title=r["title"],
            attributes=r["attrs"],
            entities_json=[{"type": "ORG", "canonical_name": r["org"]}],
            is_primary=True,
        )
    )
    note("added " + r["org"])
    s.commit()
s.close()
note("done, 3 rows committed")
