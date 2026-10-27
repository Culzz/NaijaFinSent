"""In-memory + JSON-file store for canonical entities and their aliases.

Design
------
The store is a small graph of ``Entity`` records plus a reverse index from
normalised alias surface form -> entity. Two properties matter:

1. **One normalisation function.** :func:`normalise_alias` is used both when
   building the index and when querying it, so ``"Dangote Cement Plc."``,
   ``"DANGOTE CEMENT"`` and ``"dangote  cement"`` are one key.
2. **Ambiguity is preserved, not collapsed.** :meth:`EntityStore.find_by_alias`
   returns *all* matching entities with their alias confidence, so the resolver
   can decide that ``"Access"`` is genuinely ambiguous rather than silently
   picking one.

The seed set is hand-curated and intentionally conservative. Where a ticker's
currency is uncertain the entity's ``metadata["ticker_verified"]`` is ``False``
and the alias config carries the same flag, so nothing unverified is presented
as confirmed fact.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from datetime import date
from pathlib import Path

from naijafinsent.entity_resolution.models import (
    ALIAS_TYPES,
    Entity,
    EntityAlias,
)

__all__ = [
    "EntityStore",
    "build_seed_entities",
    "normalise_alias",
    "canonical_entity_id",
]

# Legal-form suffixes that splinter entity mentions in Nigerian reporting.
# Stripped only as a *trailing* token so "Plc" inside a name is untouched.
_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "plc", "ltd", "limited", "inc", "incorporated", "corp", "corporation",
        "co", "company", "holdings", "holding", "group", "nigeria", "nplc",
    }
)

# Tokens carrying no identity signal; dropped from the fuzzy/normalised key but
# retained in the displayed alias.
_STOPWORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "of", "and", "for", "to", "at", "in", "on", "nig", "ng"}
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_alias(text: str) -> str:
    """Canonical matching key for an alias / mention surface form.

    Steps: NFKC normalise -> lowercase -> replace ``&`` with ``and`` -> drop a
    trailing legal-form suffix run (``Plc``, ``Limited``, ...) -> strip
    punctuation -> collapse whitespace. Stopwords are *kept* here because
    ``"bank of america"`` vs ``"bank america"`` should still differ for exact
    lookup; the aggressive stopword stripping happens only inside the fuzzy key.

    Examples:
        >>> normalise_alias("Dangote Cement Plc.")
        'dangote cement'
        >>> normalise_alias("  GTBank & Co  ")
        'gtbank'
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = value.replace("&", " and ")
    value = _NON_ALNUM.sub(" ", value).strip()
    if not value:
        return ""
    tokens = value.split()
    # Peel trailing legal forms / the country token one at a time.
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def fuzzy_key(text: str) -> str:
    """Aggressive key used by the fuzzy stage: normalise + drop stopwords + sort.

    Sorting makes ``"cement dangote"`` and ``"dangote cement"`` collapse, which
    matters for paraphrase and headline word-order variation.
    """
    base = normalise_alias(text)
    if not base:
        return ""
    tokens = [t for t in base.split() if t not in _STOPWORDS]
    return " ".join(sorted(tokens or base.split()))


def canonical_entity_id(canonical_name: str, primary_type: str = "ORG") -> str:
    """Deterministic ``type:slug`` id, stable across rebuilds."""
    normalised = unicodedata.normalize("NFKC", canonical_name).lower()
    slug = re.sub(r"-{2,}", "-", _NON_ALNUM.sub("-", normalised)).strip("-")
    return f"{primary_type.lower()}:{slug or 'unknown'}"


class EntityStore:
    """Entities + aliases with a normalised reverse index and JSON persistence.

    The store is mutable and cheap: ``add_entity`` / ``add_alias`` re-index
    incrementally, ``MERGE`` folds one entity into another (the common case when
    two seed entries turn out to be the same company), and ``save``/``load``
    round-trip to a single JSON document that mirrors the DB tables.
    """

    def __init__(
        self,
        entities: list[Entity] | None = None,
        aliases: list[EntityAlias] | None = None,
    ) -> None:
        self.entities: dict[str, Entity] = {}
        self.aliases: dict[str, EntityAlias] = {}          # alias_id -> alias
        self._by_norm: dict[str, list[str]] = {}           # normalised -> [alias_id]
        self._next_alias_seq = 0
        if entities or aliases:
            for ent in entities or []:
                self.add_entity(ent, _defer_index=True)
            for alias in aliases or []:
                self.add_alias(alias)
            self._reindex()

    # -- construction ---------------------------------------------------
    @classmethod
    def with_seed(cls) -> EntityStore:
        """Store pre-loaded with :func:`build_seed_entities`."""
        store = cls()
        entities, aliases = build_seed_entities()
        for ent in entities:
            store.add_entity(ent)
        for alias in aliases:
            store.add_alias(alias)
        return store

    # -- entities -------------------------------------------------------
    def add_entity(self, entity: Entity, *, _defer_index: bool = False) -> Entity:
        if not entity.entity_id:
            entity = replace(
                entity,
                entity_id=canonical_entity_id(entity.canonical_name, entity.primary_type),
            )
        self.entities[entity.entity_id] = entity
        if not _defer_index:
            # Every entity gets a legal-name alias so "Dangote Cement Plc" resolves
            # even when only the canonical name was registered.
            self.add_alias(
                EntityAlias(
                    alias=entity.canonical_name,
                    entity_id=entity.entity_id,
                    alias_type="legal_name",
                    source="canonical",
                    confidence=1.0,
                )
            )
        return entity

    def get(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def all_entities(self) -> list[Entity]:
        return list(self.entities.values())

    def by_type(self, primary_type: str) -> list[Entity]:
        return [e for e in self.entities.values() if e.primary_type == primary_type]

    def find_by_ticker(self, ticker: str) -> list[Entity]:
        """All entities carrying ``ticker`` (case-insensitive). May be > 1."""
        want = ticker.strip().upper()
        return [e for e in self.entities.values() if want in {t.upper() for t in e.tickers}]

    # -- aliases --------------------------------------------------------
    def add_alias(self, alias: EntityAlias) -> EntityAlias:
        if alias.alias_type not in ALIAS_TYPES:
            alias = replace(alias, alias_type="name")
        self._next_alias_seq += 1
        alias_id = f"{alias.entity_id}::{self._next_alias_seq}"
        self.aliases[alias_id] = alias
        key = normalise_alias(alias.alias)
        if key:
            self._by_norm.setdefault(key, []).append(alias_id)
        return alias

    def aliases_for(self, entity_id: str) -> list[EntityAlias]:
        return [a for a in self.aliases.values() if a.entity_id == entity_id]

    def find_by_alias(
        self, mention: str, *, reference_date: date | None = None
    ) -> list[tuple[Entity, EntityAlias]]:
        """Exact normalised matches for ``mention``, best confidence first.

        Returns *every* candidate: callers decide whether a single hit is a
        resolution or whether two hits mean the mention is ambiguous. Aliases
        outside their validity window (relative to ``reference_date``) are
        skipped so "FBNH" does not resolve in 2026 text.
        """
        key = normalise_alias(mention)
        if not key:
            return []
        out: list[tuple[Entity, EntityAlias]] = []
        for alias_id in self._by_norm.get(key, []):
            alias = self.aliases[alias_id]
            if not alias.is_active_on(reference_date):
                continue
            entity = self.entities.get(alias.entity_id)
            if entity is None:
                continue
            out.append((entity, alias))
        out.sort(key=lambda pair: (-pair[1].confidence, pair[0].entity_id))
        return out

    def all_surface_forms(self) -> list[tuple[str, EntityAlias]]:
        """``(normalised_surface, alias)`` pairs, for fuzzy candidate generation."""
        pairs: list[tuple[str, EntityAlias]] = []
        for key, alias_ids in self._by_norm.items():
            for alias_id in alias_ids:
                pairs.append((key, self.aliases[alias_id]))
        return pairs

    # -- merge ----------------------------------------------------------
    def merge(self, source_id: str, target_id: str) -> Entity:
        """Fold ``source_id`` into ``target_id``; return the surviving entity.

        Aliases are repointed (never copied), tickers/sectors/validity are
        unioned, and the absorbed canonical name is kept as a ``former_name``
        alias so old text still resolves -- and old *predictions* remain
        explainable after the merge.
        """
        if source_id not in self.entities:
            raise KeyError(f"unknown source entity: {source_id}")
        if target_id not in self.entities:
            raise KeyError(f"unknown target entity: {target_id}")
        if source_id == target_id:
            return self.entities[target_id]

        source = self.entities.pop(source_id)
        target = self.entities[target_id]

        target.tickers = _dedupe([*target.tickers, *source.tickers])
        target.sectors = _dedupe([*target.sectors, *source.sectors])
        if source.validity_start and (
            target.validity_start is None or source.validity_start < target.validity_start
        ):
            target.validity_start = source.validity_start
        target.metadata = {**source.metadata, **target.metadata}
        target.metadata.setdefault("merged_from", [])
        target.metadata["merged_from"] = _dedupe(
            [*target.metadata["merged_from"], source_id, source.canonical_name]
        )

        for alias_id, alias in list(self.aliases.items()):
            if alias.entity_id == source_id:
                alias.entity_id = target_id
        self.add_alias(
            EntityAlias(
                alias=source.canonical_name,
                entity_id=target_id,
                alias_type="former_name",
                source=f"merge:{source_id}",
                confidence=0.9,
            )
        )
        self._reindex()
        return target

    # -- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "entities": [e.to_dict() for e in self.entities.values()],
            "aliases": [a.to_dict() for a in self.aliases.values()],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> EntityStore:
        """Load a store written by :meth:`save`.

        Missing or malformed files raise: silently falling back to a seed set
        here would hide a corrupt artifact behind plausible-looking entity links.
        """
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        store = cls()
        for raw in data.get("entities", []):
            store.add_entity(Entity.from_dict(raw))
        for raw in data.get("aliases", []):
            alias = EntityAlias.from_dict(raw)
            if alias.entity_id in store.entities:
                store.add_alias(alias)
        return store

    # -- internals ------------------------------------------------------
    def _reindex(self) -> None:
        self._by_norm = {}
        stored = list(self.aliases.items())
        self.aliases = {}
        self._next_alias_seq = 0
        for _, alias in stored:
            self.add_alias(alias)

    def __len__(self) -> int:
        return len(self.entities)

    def __contains__(self, entity_id: object) -> bool:
        return entity_id in self.entities


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen)


# --------------------------------------------------------------------------
# Seed entities
# --------------------------------------------------------------------------
# Verification discipline
# -----------------------
# ``ticker_verified`` is True only for tickers cross-checked against the shared
# ``data/annotation/lexicon.v1.json`` (itself cross-checked against the NGX
# equities list) or otherwise certain. Where a plausible ticker could not be
# confirmed it is still recorded -- a wrong link is worse than a gap -- but the
# flag is False and the resolver lowers its confidence.
_VERIFIED = "reviewed"
_UNVERIFIED = "pending"


def _mk(
    canonical: str,
    primary_type: str,
    *,
    tickers: list[str] | None = None,
    sectors: list[str] | None = None,
    aliases: list[tuple[str, str]] | None = None,
    ticker_verified: bool = True,
    notes: str | None = None,
    country: str = "NG",
    entity_id: str | None = None,
    validity_start: date | None = None,
    validity_end: date | None = None,
    extra_metadata: dict[str, object] | None = None,
) -> tuple[Entity, list[EntityAlias]]:
    """Build one seed entity plus its aliases (internal helper)."""
    tickers = tickers or []
    metadata: dict[str, object] = {
        "ticker_verified": ticker_verified,
        "review_status": _VERIFIED if ticker_verified else _UNVERIFIED,
        "source": "seed",
    }
    if notes:
        metadata["notes"] = notes
    if extra_metadata:
        metadata.update(extra_metadata)
    entity = Entity(
        entity_id=entity_id or canonical_entity_id(canonical, primary_type),
        canonical_name=canonical,
        primary_type=primary_type,
        tickers=list(tickers),
        sectors=list(sectors or []),
        validity_start=validity_start,
        validity_end=validity_end,
        metadata=metadata,
        country=country,
    )
    out_aliases: list[EntityAlias] = []
    for alias_text, alias_type in aliases or []:
        # A ticker alias inherits the entity's verification flag, so an
        # unverified ticker can never sneak in as a confident exact match.
        confidence = 1.0
        if alias_type == "ticker" and not ticker_verified:
            confidence = 0.7
        out_aliases.append(
            EntityAlias(
                alias=alias_text,
                entity_id=entity.entity_id,
                alias_type=alias_type,
                source="seed",
                confidence=confidence,
                metadata={"ticker_verified": ticker_verified} if alias_type == "ticker" else {},
            )
        )
    return entity, out_aliases


def build_seed_entities() -> tuple[list[Entity], list[EntityAlias]]:
    """Curated Nigerian seed entity set with aliases.

    Coverage, in order: monetary / capital-market / power / pension regulators,
    the exchange and its listed operator, the listed banks and holdcos, the
    large industrials, telecoms and energy names, plus the sector labels that
    events and entity-sentiment attach to.

    Returned as ``(entities, aliases)`` rather than a prebuilt store so callers
    can post-process (merge, filter by date) before indexing.
    """
    entities: list[Entity] = []
    aliases: list[EntityAlias] = []

    def add(spec: tuple[Entity, list[EntityAlias]]) -> None:
        entity, entity_aliases = spec
        entities.append(entity)
        aliases.extend(entity_aliases)

    # -- Regulators ----------------------------------------------------
    add(
        _mk(
            "Central Bank of Nigeria",
            "REGULATOR",
            sectors=["banking"],
            aliases=[
                ("CBN", "abbreviation"),
                ("the CBN", "nickname"),
                ("apex bank", "nickname"),
                ("Central Bank", "name"),
                ("Monetary Policy Committee", "name"),
                ("MPC", "abbreviation"),
            ],
            notes="Monetary authority. Regulator, never typed ORG.",
        )
    )
    add(
        _mk(
            "Securities and Exchange Commission",
            "REGULATOR",
            sectors=["capital markets"],
            aliases=[
                ("SEC", "abbreviation"),
                ("SEC Nigeria", "name"),
                ("Nigeria SEC", "name"),
            ],
            notes="Capital-markets regulator; 'Nigeria' disambiguates from the US SEC.",
        )
    )
    add(
        _mk(
            "Nigeria Deposit Insurance Corporation",
            "REGULATOR",
            aliases=[("NDIC", "abbreviation")],
            notes="Deposit insurer for banks.",
        )
    )
    add(
        _mk(
            "Nigerian Exchange Group",
            "REGULATOR",
            tickers=["NGXGROUP"],
            sectors=["capital markets"],
            aliases=[
                ("NGX", "abbreviation"),
                ("Nigerian Exchange", "name"),
                ("Nigerian Stock Exchange", "name"),
                ("NSE", "former_name"),
                ("NGXGROUP", "ticker"),
                ("Nigerian Exchange Group Plc", "legal_name"),
            ],
            notes=(
                "Regulator/self-regulatory operator of the exchange. The listed "
                "holdco carries ticker NGXGROUP; 'NGX' alone is the exchange."
            ),
        )
    )
    add(
        _mk(
            "Nigerian Electricity Regulatory Commission",
            "REGULATOR",
            sectors=["power"],
            aliases=[("NERC", "abbreviation")],
            notes="Power-sector regulator.",
        )
    )
    add(
        _mk(
            "Federal Competition and Consumer Protection Commission",
            "REGULATOR",
            aliases=[("FCCPC", "abbreviation"), ("FCCPC Nigeria", "name")],
            notes="Competition and consumer-protection regulator.",
        )
    )
    add(
        _mk(
            "National Pension Commission",
            "REGULATOR",
            aliases=[("PenCom", "abbreviation"), ("PENCOM", "abbreviation")],
            notes="Pension-industry regulator.",
        )
    )

    # -- Banks / holdcos -----------------------------------------------
    add(
        _mk(
            "Dangote Cement Plc",
            "ORG",
            tickers=["DANGCEM"],
            sectors=["cement", "industrial goods"],
            aliases=[
                ("Dangote Cement", "name"),
                ("DANGCEM", "ticker"),
                ("Dangote Cem", "abbreviation"),
                ("the cement maker", "description"),
                ("Dangote", "nickname"),
            ],
            notes="Ticker confirmed against the shared lexicon / NGX list.",
        )
    )
    add(
        _mk(
            "MTN Nigeria Communications Plc",
            "ORG",
            tickers=["MTNN"],
            sectors=["telecoms"],
            aliases=[
                ("MTN Nigeria", "name"),
                ("MTN", "nickname"),
                ("MTNN", "ticker"),
                ("the telco", "description"),
            ],
        )
    )
    # JSE-listed parent — deliberately a separate entity so "MTN Group"
    # news is never booked onto the Nigerian subsidiary's timeline.
    # No ticker registered: the JSE code "MTN" collides with the Nigerian
    # alias index and the ambiguous path is the honest answer for bare "MTN".
    add(
        _mk(
            "MTN Group Plc",
            "ORG",
            tickers=[],
            sectors=["telecoms"],
            aliases=[
                ("MTN Group", "name"),
                ("MTN Group Limited", "legal_name"),
                ("MTN Group Holdings", "name"),
            ],
        )
    )
    add(
        _mk(
            "Guaranty Trust Holding Company Plc",
            "ORG",
            tickers=["GTCO"],
            sectors=["banking"],
            aliases=[
                ("Guaranty Trust", "name"),
                ("Guaranty Trust Bank", "name"),
                ("GTBank", "nickname"),
                ("GTCO", "ticker"),
                ("GTCO Plc", "legal_name"),
            ],
            notes="Holdco ticker; the operating bank itself is GTBank.",
        )
    )
    add(
        _mk(
            "Zenith Bank Plc",
            "ORG",
            tickers=["ZENITHBANK"],
            sectors=["banking"],
            aliases=[
                ("Zenith Bank", "name"),
                ("Zenith", "nickname"),
                ("ZENITHBANK", "ticker"),
            ],
        )
    )
    add(
        _mk(
            "Airtel Africa Plc",
            "ORG",
            tickers=["AIRTELAFRI"],
            sectors=["telecoms"],
            aliases=[
                ("Airtel Africa", "name"),
                ("Airtel", "nickname"),
                ("AIRTELAFRI", "ticker"),
            ],
        )
    )
    add(
        _mk(
            "BUA Cement Plc",
            "ORG",
            tickers=["BUACEMENT"],
            sectors=["cement", "industrial goods"],
            aliases=[
                ("BUA Cement", "name"),
                ("BUA", "nickname"),
                ("BUACEMENT", "ticker"),
            ],
            notes="'BUA' alone also refers to BUA Foods; treated as a collision.",
        )
    )
    add(
        _mk(
            "Nigerian Breweries Plc",
            "ORG",
            tickers=["NB"],
            sectors=["consumer goods"],
            aliases=[
                ("Nigerian Breweries", "name"),
                ("NB", "ticker"),
            ],
            notes="Ambiguous with 'nota bene' outside market context.",
        )
    )
    add(
        _mk(
            "United Bank for Africa Plc",
            "ORG",
            tickers=["UBA"],
            sectors=["banking"],
            aliases=[
                ("United Bank for Africa", "name"),
                ("UBA Plc", "legal_name"),
                ("UBA", "ticker"),
                ("UBA Group", "name"),
                ("the pan-African lender", "description"),
            ],
            notes="Ticker confirmed (NOT 'UBACEMPTY'). Also an acronym collision.",
        )
    )
    add(
        _mk(
            "Access Holdings Plc",
            "ORG",
            tickers=["ACCESSCORP"],
            sectors=["banking"],
            aliases=[
                ("Access Holdings", "name"),
                ("Access Bank", "name"),
                ("Access Corporation", "name"),
                ("ACCESSCORP", "ticker"),
                ("Access", "nickname"),
                ("Diamond Bank", "former_name"),
            ],
            notes="Access Bank is the subsidiary; ACCESSCORP the listed holdco.",
        )
    )
    add(
        _mk(
            "Fidelity Bank Plc",
            "ORG",
            tickers=["FIDELITYBK"],
            sectors=["banking"],
            aliases=[
                ("Fidelity Bank", "name"),
                ("Fidelity", "nickname"),
                ("FIDELITYBK", "ticker"),
            ],
        )
    )
    add(
        _mk(
            "Stanbic IBTC Holdings Plc",
            "ORG",
            tickers=["STANBIC"],
            sectors=["banking"],
            aliases=[
                ("Stanbic IBTC", "name"),
                ("Stanbic IBTC Holdings", "legal_name"),
                ("Stanbic", "nickname"),
                ("STANBIC", "ticker"),
            ],
        )
    )
    # First Bank / First HoldCo: the corporate history here is genuinely messy,
    # so both the current and the legacy identity are recorded with dates and
    # the legacy ticker is marked unverified for current text.
    add(
        _mk(
            "First HoldCo Plc",
            "ORG",
            tickers=["FIRSTHOLDCO"],
            sectors=["banking"],
            aliases=[
                ("First HoldCo", "name"),
                ("FirstHoldCo", "name"),
                ("First Bank", "name"),
                ("First Bank of Nigeria", "name"),
                ("FirstBank", "nickname"),
                ("FIRSTHOLDCO", "ticker"),
            ],
            ticker_verified=False,
            validity_start=date(2025, 1, 1),
            notes=(
                "Successor to FBN Holdings after the 2025 restructure. Ticker "
                "FIRSTHOLDCO not confirmed against the shared lexicon; marked unverified."
            ),
        )
    )
    add(
        _mk(
            "FBN Holdings Plc",
            "ORG",
            tickers=["FBNH"],
            sectors=["banking"],
            aliases=[
                ("FBN Holdings", "name"),
                ("FBNH", "ticker"),
            ],
            ticker_verified=False,
            validity_end=date(2024, 12, 31),
            notes=(
                "LEGACY identity superseded by First HoldCo. Kept with "
                "validity_end so pre-2025 text still resolves and post-2025 text does not."
            ),
        )
    )

    # -- Energy / industrial -------------------------------------------
    add(
        _mk(
            "Seplat Energy Plc",
            "ORG",
            tickers=["SEPLAT"],
            sectors=["oil and gas", "energy"],
            aliases=[
                ("Seplat Energy", "name"),
                ("Seplat", "nickname"),
                ("SEPLAT", "ticker"),
            ],
        )
    )
    add(
        _mk(
            "Oando Plc",
            "ORG",
            tickers=["OANDO"],
            sectors=["oil and gas", "energy"],
            aliases=[("Oando", "name"), ("OANDO", "ticker")],
        )
    )
    add(
        _mk(
            "TotalEnergies Marketing Nigeria Plc",
            "ORG",
            tickers=["TOTAL"],
            sectors=["oil and gas", "energy"],
            aliases=[
                ("TotalEnergies", "name"),
                ("TotalEnergies Marketing", "name"),
                ("Total Nigeria", "name"),
                ("Total", "nickname"),
                ("TOTAL", "ticker"),
            ],
            notes="Downstream marketing arm; 'Total' also appears as a generic quantifier.",
        )
    )
    add(
        _mk(
            "Transnational Corporation Plc",
            "ORG",
            tickers=["TRANSCORP"],
            sectors=["conglomerate", "power"],
            aliases=[
                ("Transcorp", "name"),
                ("Transnational Corporation", "name"),
                ("TRANSCORP", "ticker"),
            ],
            notes="Distinct from Transcorp Power (TRANSPOWER).",
        )
    )
    add(
        _mk(
            "Lafarge Africa Plc",
            "ORG",
            tickers=["WAPCO"],
            sectors=["cement", "industrial goods"],
            aliases=[
                ("Lafarge Africa", "name"),
                ("Lafarge", "nickname"),
                ("WAPCO", "ticker"),
                ("the cement giant", "description"),
            ],
            notes="NGX ticker is WAPCO, NOT 'LAFARGE'.",
        )
    )

    # -- Sectors (typed SECTOR, never ORG) -----------------------------
    for canonical, sector_aliases in (
        ("banking", ["banks", "banking sector", "the banking sector", "lenders"]),
        ("oil and gas", ["oil & gas", "oil and gas sector", "upstream", "downstream"]),
        ("cement", ["cement sector", "cement makers"]),
        ("telecoms", ["telecommunications", "telecom", "telcos"]),
        ("power", ["electricity", "energy sector", "power sector"]),
        ("capital markets", ["capital market", "stock market", "equities market"]),
    ):
        add(
            _mk(
                canonical,
                "SECTOR",
                aliases=[(a, "name") for a in sector_aliases],
                notes="Sector label; never a company.",
            )
        )

    return entities, aliases
