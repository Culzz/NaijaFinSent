"""Deduplication utilities live in :mod:`naijafinsent.data.dedup`.

This package is a thin, stable import surface so callers can write
``from naijafinsent.deduplication import Deduplicator`` without caring which
module inside ``naijafinsent.data`` implements it.
"""

from __future__ import annotations

from naijafinsent.data.dedup import (  # noqa: F401
    Deduplicator,
    find_near_duplicates,
)

__all__ = ["Deduplicator", "find_near_duplicates"]
