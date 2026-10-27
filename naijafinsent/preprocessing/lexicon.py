"""Lexicon-backed entity matching -- the no-model NER bootstrap.

Loads ``data/annotation/lexicon.v1.json`` (authored elsewhere) when present and
otherwise uses a small embedded fallback covering the most important Nigerian
financial entities. Both paths expose the same :class:`Lexicon` API so callers
never branch on file presence.

Matching is longest-match and word-boundary aware, so ``"GTBank"`` and
``"Guaranty Trust"`` resolve to the same canonical entity while ``"Access"`` in
``"Access Bank"`` does not spuriously fire inside ``"Accessible"``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from naijafinsent.schemas import EntitySpan, EntityType

__all__ = ["LexiconEntry", "Lexicon", "load_default_lexicon", "DEFAULT_LEXICON_PATH"]


DEFAULT_LEXICON_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "annotation" / "lexicon.v1.json"
)


@dataclass
class LexiconEntry:
    """One canonical entity and its surface aliases."""

    canonical: str
    entity_type: EntityType
    aliases: tuple[str, ...] = ()
    ticker: str | None = None
    notes: str | None = None

    @property
    def surfaces(self) -> tuple[str, ...]:
        """All surface forms (canonical + aliases + ticker), longest first."""
        forms = [self.canonical, *self.aliases]
        if self.ticker:
            forms.append(self.ticker)
        seen: dict[str, None] = {}
        for f in forms:
            f = f.strip()
            if f:
                seen.setdefault(f, None)
        return tuple(sorted(seen.keys(), key=len, reverse=True))


# --- Embedded fallback --------------------------------------------------------
# Kept small and factual; the real lexicon is data-driven and versioned.
_FALLBACK_RAW: list[dict[str, object]] = [
    # Regulators
    {"canonical": "Central Bank of Nigeria", "type": "REGULATOR",
     "aliases": ["CBN", "the CBN", "apex bank"]},
    {"canonical": "Securities and Exchange Commission", "type": "REGULATOR",
     "aliases": ["SEC", "SEC Nigeria"]},
    {"canonical": "Nigeria Deposit Insurance Corporation", "type": "REGULATOR",
     "aliases": ["NDIC"]},
    {"canonical": "Nigerian Exchange Group", "type": "REGULATOR",
     "aliases": ["NGX", "Nigerian Exchange", "NSE", "Nigerian Stock Exchange"]},
    {"canonical": "Federal Competition and Consumer Protection Commission",
     "type": "REGULATOR", "aliases": ["FCCPC"]},
    {"canonical": "National Pension Commission", "type": "REGULATOR",
     "aliases": ["PenCom", "PENCOM"]},
    {"canonical": "Nigerian Electricity Regulatory Commission", "type": "REGULATOR",
     "aliases": ["NERC"]},
    {"canonical": "Federal Inland Revenue Service", "type": "REGULATOR",
     "aliases": ["FIRS"]},
    {"canonical": "Nigerian Communications Commission", "type": "REGULATOR",
     "aliases": ["NCC"]},
    # Banks
    {"canonical": "Guaranty Trust Holding Company", "type": "ORG",
     "aliases": ["GTCO", "Guaranty Trust", "GTBank", "Guaranty Trust Bank"],
     "ticker": "GTCO"},
    {"canonical": "Zenith Bank", "type": "ORG", "aliases": ["Zenith"], "ticker": "ZENITHBANK"},
    {"canonical": "Access Holdings", "type": "ORG",
     "aliases": ["Access Bank", "Access Corporation"], "ticker": "ACCESSCORP"},
    {"canonical": "United Bank for Africa", "type": "ORG", "aliases": ["UBA"], "ticker": "UBA"},
    {"canonical": "First Bank of Nigeria", "type": "ORG",
     "aliases": ["First Bank", "FirstBank", "FBN Holdings", "FBNH"], "ticker": "FBNH"},
    {"canonical": "Stanbic IBTC Holdings", "type": "ORG",
     "aliases": ["Stanbic IBTC", "Stanbic"], "ticker": "STANBIC"},
    {"canonical": "Fidelity Bank", "type": "ORG", "aliases": ["Fidelity"], "ticker": "FIDELITYBK"},
    {"canonical": "Sterling Bank", "type": "ORG", "aliases": ["Sterling"], "ticker": "STERLINGNG"},
    # Industrial / telecom / energy
    {"canonical": "Dangote Cement", "type": "ORG", "aliases": ["Dangote"], "ticker": "DANGCEM"},
    {"canonical": "MTN Nigeria", "type": "ORG", "aliases": ["MTN"], "ticker": "MTNN"},
    {"canonical": "Airtel Africa", "type": "ORG", "aliases": ["Airtel"], "ticker": "AIRTELAFRI"},
    {"canonical": "BUA Cement", "type": "ORG", "aliases": ["BUA"], "ticker": "BUACEMENT"},
    {"canonical": "Nestle Nigeria", "type": "ORG", "aliases": ["Nestl\u00e9 Nigeria", "Nestle"],
     "ticker": "NESTLE"},
    {"canonical": "Nigerian Breweries", "type": "ORG", "aliases": ["NB"], "ticker": "NB"},
    {"canonical": "Oando Plc", "type": "ORG", "aliases": ["Oando"], "ticker": "OANDO"},
    {"canonical": "Seplat Energy", "type": "ORG", "aliases": ["Seplat"], "ticker": "SEPLAT"},
    {"canonical": "Nigerian National Petroleum Company", "type": "ORG",
     "aliases": ["NNPC", "NNPC Limited", "NNPCL"]},
    {"canonical": "Transcorp", "type": "ORG", "aliases": ["Transnational Corporation"],
     "ticker": "TRANSCORP"},
    # People commonly in the news
    {"canonical": "Olayemi Cardoso", "type": "PER", "aliases": ["Cardoso"]},
    {"canonical": "Bola Ahmed Tinubu", "type": "PER", "aliases": ["Tinubu", "Bola Tinubu"]},
    {"canonical": "Aliko Dangote", "type": "PER", "aliases": []},
    # Sectors
    {"canonical": "banking", "type": "SECTOR", "aliases": ["banks", "banking sector"]},
    {"canonical": "oil and gas", "type": "SECTOR",
     "aliases": ["oil & gas", "oil and gas sector", "upstream", "downstream"]},
    {"canonical": "telecoms", "type": "SECTOR",
     "aliases": ["telecommunications", "telecom", "telcos"]},
    {"canonical": "cement", "type": "SECTOR", "aliases": ["cement sector"]},
    {"canonical": "agriculture", "type": "SECTOR", "aliases": ["agribusiness", "agro"]},
    {"canonical": "power", "type": "SECTOR", "aliases": ["electricity", "energy sector"]},
]


def _entry_from_raw(raw: dict[str, object]) -> LexiconEntry:
    type_str = str(raw.get("type", "ORG")).upper()
    try:
        etype = EntityType(type_str)
    except ValueError:
        etype = EntityType.ORG
    aliases_raw = raw.get("aliases", [])
    aliases = tuple(str(a) for a in aliases_raw) if isinstance(aliases_raw, list) else ()
    ticker = raw.get("ticker")
    # The committed lexicon stores its own surface term; treat it as an alias
    # when it differs from the canonical name.
    term = raw.get("term")
    if term:
        t = str(term)
        if t.upper() != t and t != str(raw.get("canonical", "")):
            aliases = (t, *aliases)
        if t.upper() == t and not ticker:
            ticker = t
    return LexiconEntry(
        canonical=str(raw["canonical"]),
        entity_type=etype,
        aliases=aliases,
        ticker=str(ticker) if ticker else None,
        notes=str(raw["notes"]) if raw.get("notes") else None,
    )


def _build_surface_index(entries: list[LexiconEntry]) -> dict[str, tuple[LexiconEntry, bool]]:
    """Map lowercased surface form -> (entry, is_ticker)."""
    index: dict[str, tuple[LexiconEntry, bool]] = {}
    for e in entries:
        surfaces = [e.canonical, *e.aliases]
        if e.ticker:
            surfaces.append(e.ticker)
        for s in surfaces:
            s = s.strip()
            if not s:
                continue
            index[s.lower()] = (e, e.ticker is not None and s.lower() == e.ticker.lower())
    return index


@dataclass
class Lexicon:
    """Longest-match, word-boundary-aware entity matcher.

    Load with :meth:`from_file` (returns a fallback-backed lexicon if the file
    is missing) or construct directly from entries for tests.
    """

    entries: list[LexiconEntry] = field(default_factory=list)
    source: str = "fallback"
    _index: dict[str, tuple[LexiconEntry, bool]] = field(default_factory=dict, repr=False)
    _max_surface_len: int = field(default=1, repr=False)

    def __post_init__(self) -> None:
        if not self._index:
            self._index = _build_surface_index(self.entries)
        if self._index:
            self._max_surface_len = max(len(k) for k in self._index)

    # -- constructors ---------------------------------------------------
    @classmethod
    def from_raw(cls, raw_entries: list[dict[str, object]], *, source: str = "inline") -> Lexicon:
        return cls(entries=[_entry_from_raw(r) for r in raw_entries], source=source)

    @classmethod
    def from_file(cls, path: Path | None = None) -> Lexicon:
        """Load the lexicon JSON, degrading to the embedded fallback if absent.

        Accepts two shapes: a top-level list of entries, or an object with an
        ``"entities"``/``"entries"`` list. Unknown fields are ignored.
        """
        path = path or DEFAULT_LEXICON_PATH
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = data
                if isinstance(data, dict):
                    # The committed lexicon uses "terms"; tolerate other shapes.
                    raw = data.get("entities") or data.get("entries") or data.get("terms") or []
                if isinstance(raw, list) and raw:
                    entries = [_entry_from_raw(r) for r in raw if isinstance(r, dict)]
                    if entries:
                        return cls(entries=entries, source=str(path))
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                # Fall through to fallback rather than crash the pipeline.
                pass
        return cls.from_raw(_FALLBACK_RAW, source="embedded-fallback")

    @classmethod
    def fallback(cls) -> Lexicon:
        return cls.from_raw(_FALLBACK_RAW, source="embedded-fallback")

    # -- matching -------------------------------------------------------
    def _boundary_pattern(self, surface: str) -> re.Pattern[str]:
        """Word-boundary-aware pattern for a surface form.

        Boundaries are asserted only where the surface edge is a word
        character, so tickers like ``"NB"`` match as whole tokens but
        punctuation-adjacent forms still match.
        """
        escaped = re.escape(surface)
        left = r"(?<!\w)" if surface[0].isalnum() else ""
        right = r"(?!\w)" if surface[-1].isalnum() else ""
        # Allow flexible internal whitespace.
        escaped = re.sub(r"\\?\s+", r"\\s+", escaped)
        return re.compile(left + escaped + right, re.IGNORECASE)

    def match(self, text: str) -> list[EntitySpan]:
        """Return all lexicon mentions in ``text`` as ``EntitySpan`` objects.

        Longest-match-first: candidates are tried from the longest surface form
        down, and a match is only accepted if it does not overlap an already
        accepted span. This means ``"Guaranty Trust Bank"`` wins over
        ``"Guaranty Trust"`` and over the ticker ``"GTCO"`` (which wouldn't
        overlap anyway).
        """
        if not text:
            return []

        # Collect all candidate matches with their char spans.
        candidates: list[tuple[int, int, LexiconEntry]] = []
        for surface, (entry, _is_ticker) in self._index.items():
            for m in self._boundary_pattern(surface).finditer(text):
                candidates.append((m.start(), m.end(), entry))
        # Longest span first, then leftmost, for deterministic non-overlap.
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

        accepted: list[tuple[int, int, LexiconEntry]] = []
        for start, end, entry in candidates:
            if any(not (end <= s or start >= e) for s, e, _ in accepted):
                continue
            accepted.append((start, end, entry))

        accepted.sort(key=lambda c: c[0])
        return [
            EntitySpan(
                start=s,
                end=e,
                text=text[s:e],
                entity_type=entry.entity_type,
            )
            for s, e, entry in accepted
        ]

    def match_with_canonical(self, text: str) -> list[tuple[EntitySpan, str]]:
        """Like :meth:`match` but pairs each span with its canonical name."""
        spans = self.match(text)
        out: list[tuple[EntitySpan, str]] = []
        for span in spans:
            entry, _ = self._index.get(span.text.lower(), (None, False))
            canonical = entry.canonical if entry is not None else span.text
            out.append((span, canonical))
        return out

    def lookup(self, surface: str) -> LexiconEntry | None:
        """Canonical entry for a surface form, or ``None``."""
        hit = self._index.get((surface or "").strip().lower())
        return hit[0] if hit else None

    def __len__(self) -> int:
        return len(self.entries)


def load_default_lexicon() -> Lexicon:
    """Convenience loader used by the rule-based NER baseline."""
    return Lexicon.from_file()
