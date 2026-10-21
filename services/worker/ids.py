"""Identifier helpers shared by the worker and the API services.

Run ids are prefixed and time-ordered so that ``ls``/``grep`` over logs and
``inference_runs.run_id`` sorts chronologically without parsing timestamps.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def new_run_id(prefix: str) -> str:
    """Return e.g. ``ingest_20260120T141503_a1b2c3``.

    The random suffix prevents collisions when two workers start in the same
    second, which happens routinely when a scheduler retries immediately.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}_{stamp}_{secrets.token_hex(3)}"


__all__ = ["new_run_id"]
