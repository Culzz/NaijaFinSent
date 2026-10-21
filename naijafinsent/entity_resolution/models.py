"""Lightweight, framework-free dataclasses for the entity-resolution layer.

Why not pydantic here
---------------------
``naijafinsent.schemas`` owns the *wire* shapes (``EntityPrediction`` and
friends) and is validated on every API boundary. The entity layer instead holds
a few thousand records that are loaded once, indexed, and queried in a tight
loop; pydantic's per-instance validation is pure overhead there. These are plain
dataclasses, deliberately mirroring the columns of
``services.api.app.db.models.Entity`` / ``EntityAlias`` so a store can be
serialised to the DB later without a second mapping layer.

Point-in-time correctness
-------------------------
Nigerian corporate identity is not stable: Diamond Bank was absorbed into
Access Bank, ``FBNH`` was retired in favour of ``FIRSTHOLDCO``, and "Access
Bank" is the subsidiary while "ACCESSCORP" is the listed holdco. Every entity
and alias therefore carries ``validity_start`` / ``validity_end``, and calling
code is expected to pass the article's publish date as the reference point when
it wants a point-in-time answer. ``validity_end=None`` means "still current".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

__all__ = [
    "Entity",
    "EntityAlias",
    "ResolutionResult",
    "ALIAS_TYPES",
    "RESOLUTION_METHODS",
]


# Allowed ``alias_type`` values. Kept as plain strings (not an Enum) so unknown
# values survive a round-trip through JSON and the DB instead of raising.
ALIAS_TYPES: tuple[str, ...] = (
    "legal_name",
    "name",
    "abbreviation",
    "ticker",
    "nickname",
    "former_name",
    "description",  # "the cement maker", "the lender" -- paraphrastic references
    "descriptor",
)

# The method labels written into ``EntityPrediction.resolution_method``. The
# SRS pins this vocabulary: {alias, fuzzy, embedding, context, ambiguous, none}.
RESOLUTION_METHODS: tuple[str, ...] = (
    "alias",
    "fuzzy",
    "embedding",
    "context",
    "ambiguous",
    "none",
)


@dataclass(slots=True)
class Entity:
    """A canonical real-world entity (company, regulator, person, sector).

    ``entity_id`` is a stable slug (e.g. ``org:dangote-cement``) rather than an
    integer: the seed set is hand-authored in Python and must stay stable across
    rebuilds and across the JSON store, since predictions reference it.

    ``tickers`` is a list because a company can carry several (``FBNH`` legacy
    plus ``FIRSTHOLDCO`` current, or a dual listing). ``metadata`` carries two
    ``ticker_verified`` flags, market codes, and any provenance note; nothing in
    ``metadata`` is load-bearing for matching, only for disclosure.
    """

    entity_id: str
    canonical_name: str
    primary_type: str = "ORG"
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    validity_start: date | None = None
    validity_end: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Not part of the required signature but genuinely needed downstream: the
    # country keeps "SEC" (Nigeria) apart from "SEC" (United States) and is
    # written into the resolution context features.
    country: str = "NG"

    # -- convenience ----------------------------------------------------
    @property
    def primary_ticker(self) -> str | None:
        return self.tickers[0] if self.tickers else None

    def is_active_on(self, when: date | None) -> bool:
        """Point-in-time membership: was this entity valid on ``when``?

        ``None`` means "no date supplied" and is treated as current-day.
        """
        if when is None:
            return self.validity_end is None
        if self.validity_start is not None and when < self.validity_start:
            return False
        if self.validity_end is not None and when > self.validity_end:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("validity_start", "validity_end"):
            value = data.get(key)
            data[key] = value.isoformat() if isinstance(value, date) else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        return cls(**_coerce_dates(data, ("validity_start", "validity_end")))


@dataclass(slots=True)
class EntityAlias:
    """A surface form that points at a canonical entity.

    ``alias`` is the *as-written* string; matching is done on a normalised form
    derived by :func:`naijafinsent.entity_resolution.store.normalise_alias`, so
    punctuation, case, and the ``Plc``/``Ltd`` suffix splintering in real
    Nigerian reporting all collapse.
    """

    alias: str
    entity_id: str
    alias_type: str = "name"
    source: str | None = None
    confidence: float = 1.0
    validity_start: date | None = None
    validity_end: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active_on(self, when: date | None) -> bool:
        if when is None:
            return self.validity_end is None
        if self.validity_start is not None and when < self.validity_start:
            return False
        if self.validity_end is not None and when > self.validity_end:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("validity_start", "validity_end"):
            value = data.get(key)
            data[key] = value.isoformat() if isinstance(value, date) else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityAlias:
        return cls(**_coerce_dates(data, ("validity_start", "validity_end")))


@dataclass(slots=True)
class ResolutionResult:
    """The outcome of resolving one mention.

    A genuinely ambiguous mention yields ``entity_id is None`` with
    ``method="ambiguous"`` and ``is_ambiguous=True`` -- never a confident link to
    an arbitrary candidate. That is a hard requirement (SRS FR-EVENT-8), so the
    dataclass makes the honest outcome the explicit one rather than a special
    case bolted on by callers.
    """

    mention_text: str
    entity_id: str | None = None
    canonical_name: str | None = None
    method: str = "none"
    confidence: float = 0.0
    is_ambiguous: bool = False
    # Kept for auditability (SRS FR-EVENT-9: expose resolution decisions): the
    # runners-up and why the winner won.
    candidates: list[tuple[str, float]] = field(default_factory=list)
    matched_alias: str | None = None
    notes: str | None = None

    @property
    def resolved(self) -> bool:
        return self.entity_id is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_dates(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Copy ``data``, turning ISO date strings back into ``date`` objects."""
    out = dict(data)
    for key in keys:
        value = out.get(key)
        if isinstance(value, str) and value:
            try:
                out[key] = date.fromisoformat(value)
            except ValueError:
                out[key] = None
    return out
