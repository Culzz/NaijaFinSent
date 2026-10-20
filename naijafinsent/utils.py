"""Small shared helpers used across the core package."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime

_WS_RE = re.compile(r"[ \t\u00a0]+")
_NL_RE = re.compile(r"\n{3,}")
_WS_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%])")


def sha256_text(text: str) -> str:
    """Hash the *normalised* content so cosmetic HTML differences collapse."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def normalise_text(text: str) -> str:
    """Canonical form used for hashing, dedup, and offset-stable annotation."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _WS_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-{2,}", "-", value).strip("-")
