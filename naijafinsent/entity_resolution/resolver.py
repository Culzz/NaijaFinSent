"""Staged entity resolver (experiment E5).

The resolver runs a **cascade of increasingly weak evidence** and stops at the
first stage that produces a defensible answer. It is deliberately not a single
similarity score, because the failure mode we care about is not "missed a
match" -- it is "confidently linked the wrong company", which is unrecoverable
downstream (a wrong entity makes a wrong timeline, a wrong sentiment aggregate
and a wrong market association).

Stages, in order
----------------
1. ``alias``     exact match against the normalised alias index.
2. ``context``   alias/fuzzy candidates filtered or promoted by context features
                 passed in by the caller (a co-occurring ticker, the source
                 country, the publisher, the sector of the article).
3. ``fuzzy``     ``rapidfuzz`` over the alias key space (WRatio / token_set_ratio).
4. ``embedding`` optional, opt-in, only if an ``embedder`` callable is injected.

Anything that survives with less than ``min_confidence`` -- or that has two
candidates within ``ambiguity_margin`` of each other -- is returned as
``method="ambiguous"`` with ``entity_id=None``. That is a stated requirement
(SRS FR-EVENT-8): the system must be able to say "I do not know".

Ticker acronym collisions
-------------------------
``"UBA"`` is a ticker, an abbreviation, and a word that appears inside other
strings. ``"Access"`` is a company, a common noun, and a bank subsidiary name.
``"NB"`` is Nigerian Breweries and ``nota bene``. ``TickerCollisionResolver``
holds the hand-authored rules for these cases and is consulted *before* a fuzzy
match is allowed to win, because fuzzy scoring actively prefers the wrong answer
here (``"UBA"`` is closer to ``"UBA Plc"`` than the gold entity is).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from naijafinsent.entity_resolution.models import (
    Entity,
    EntityAlias,
    ResolutionResult,
)
from naijafinsent.entity_resolution.store import (
    EntityStore,
    fuzzy_key,
    normalise_alias,
)
from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType

__all__ = [
    "EntityResolver",
    "TickerCollisionResolver",
    "ResolutionContext",
    "stage_alias",
    "stage_fuzzy",
    "stage_embedding",
    "STAGE_WEIGHTS",
]

# Fuzzy thresholds. These are the numbers experiment E5 sweeps; they are module
# constants (not magic literals buried in a branch) so a sweep can monkeypatch
# them or read them into a report.
DEFAULT_FUZZY_THRESHOLD: float = 88.0
DEFAULT_MIN_CONFIDENCE: float = 0.62
# Two candidates closer than this are treated as a tie -> ambiguous.
DEFAULT_AMBIGUITY_MARGIN: float = 0.08


@dataclass
class ResolutionContext:
    """Document-level hints supplied by the caller.

    All fields are optional: an empty context must degrade to pure string
    matching, never to a crash. The pipeline Protocol only promises
    ``resolve(mentions)``, so a resolver must work with no context at all --
    :class:`EntityResolver` has :meth:`resolve` as the Protocol-shaped entry
    point and :meth:`resolve_mentions` as the richer one.
    """

    text: str = ""
    tickers: tuple[str, ...] = ()          # tickers appearing elsewhere in the doc
    sectors: tuple[str, ...] = ()
    country: str | None = "NG"
    publisher: str | None = None
    reference_date: date | None = None
    # Any extra keys a caller wants to attach; exposed to custom hooks only.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tickers": list(self.tickers),
            "sectors": list(self.sectors),
            "country": self.country,
            "publisher": self.publisher,
            "reference_date": (
                self.reference_date.isoformat() if self.reference_date else None
            ),
            **self.extra,
        }


# How much each stage's raw similarity is trusted when producing a confidence.
# Alias matching is near-certain; fuzzy is a guess with a calibrated discount;
# embedding similarity is weaker still and only ever breaks ties.
STAGE_WEIGHTS: dict[str, float] = {
    "alias": 1.00,
    "context": 0.92,
    "fuzzy": 0.78,
    "embedding": 0.65,
}


# --------------------------------------------------------------------------
# Ticker / acronym collision rules
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CollisionRule:
    """A hand-authored disambiguation rule for one problematic surface form.

    ``preferred`` is the entity that should win when ``required_hints`` are all
    present in the context; ``blocked`` entities must never be returned for this
    surface form (they are *plausible* matches the fuzzy stage would otherwise
    pick); ``ambiguous_without_hint`` means: with no hint, refuse to choose.
    """

    surface: str                       # normalised surface form
    preferred: str                     # entity_id
    required_hints: tuple[str, ...] = ()   # tickers/sectors/country that settle it
    blocked: tuple[str, ...] = ()
    ambiguous_without_hint: bool = True
    rationale: str = ""


def _rule_key(text: str) -> str:
    """Strict key for collision-rule surface matching.

    Unlike :func:`~naijafinsent.entity_resolution.store.normalise_alias` —
    which peels trailing ``nigeria``/``group``/``holdings`` and therefore
    collapses ``"MTN Nigeria"``, ``"MTN Group"`` and ``"MTN"`` into the same
    key — this only strips bare legal-form suffixes. Collision surfaces that
    differ by those identity-bearing tokens stay different rules.
    """
    tokens = re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split()
    while len(tokens) > 1 and tokens[-1] in {"plc", "ltd", "limited", "inc", "nplc"}:
        tokens.pop()
    return " ".join(tokens)


class TickerCollisionResolver:
    """Rules for surfaces where the same string means different things.

    The point is precision, not recall: for ``"UBA"`` we would rather return
    *nothing* than return "UBA (legacy alias)" or the wrong bank. Rules are
    data, so they can be reviewed and extended without touching the cascade.
    """

    def __init__(self, rules: Iterable[CollisionRule] | None = None) -> None:
        self.rules: dict[str, list[CollisionRule]] = {}
        for rule in rules if rules is not None else default_collision_rules():
            self.rules.setdefault(_rule_key(rule.surface), []).append(rule)

    # -- lookup ---------------------------------------------------------
    def rule_for(self, mention: str) -> CollisionRule | None:
        hits = self.rules.get(_rule_key(mention), [])
        return hits[0] if hits else None

    def blocked_ids(self, mention: str) -> set[str]:
        return {eid for rule in self.rules.get(_rule_key(mention), []) for eid in rule.blocked}

    def preferred_with_hints(
        self, mention: str, context: ResolutionContext
    ) -> str | None:
        """Entity to prefer *only if* the context supplies the required hints.

        A rule whose surface form is itself unambiguous ("MTN Group" carries
        the word ``group``) may carry **no** hints at all -- then the surface
        alone settles it, provided the rule is not marked as refusing without
        hints.
        """
        key = _rule_key(mention)
        for rule in self.rules.get(key, []):
            if rule.required_hints and all(_hint_present(h, context) for h in rule.required_hints):
                return rule.preferred
            if not rule.required_hints and not rule.ambiguous_without_hint:
                return rule.preferred
        return None

    def is_genuinely_ambiguous(self, mention: str, context: ResolutionContext) -> bool:
        """True when a rule says "do not choose" and the context cannot settle it."""
        for rule in self.rules.get(_rule_key(mention), []):
            if not rule.ambiguous_without_hint:
                continue
            if rule.required_hints and all(_hint_present(h, context) for h in rule.required_hints):
                continue  # hints settle it
            return True
        return False


def _hint_present(hint: str, context: ResolutionContext) -> bool:
    """Is ``hint`` present in the context?

    A hint is either ``ticker:<SYM>``, ``sector:<name>``, ``country:<ISO>`` or a
    bare string checked against tickers and sectors.
    """
    tickers = {t.upper() for t in context.tickers}
    sectors = {s.lower() for s in context.sectors}
    if hint.startswith("ticker:"):
        return hint.split(":", 1)[1].upper() in tickers
    if hint.startswith("sector:"):
        return hint.split(":", 1)[1].lower() in sectors
    if hint.startswith("country:"):
        return (context.country or "").upper() == hint.split(":", 1)[1].upper()
    return hint.upper() in tickers or hint.lower() in sectors


def default_collision_rules() -> list[CollisionRule]:
    """The seed collision rules.

    Each entry documents *why* it exists; a reviewer can falsify the rationale
    against real coverage, which is the whole point of keeping them as data.
    """
    return [
        CollisionRule(
            surface="UBA",
            preferred="org:united-bank-for-africa-plc",
            required_hints=("ticker:UBA",),
            blocked=("org:united-bank-for-africa-plc::legacy",),
            ambiguous_without_hint=False,
            rationale=(
                "In Nigerian financial text 'UBA' is United Bank for Africa; the "
                "shared lexicon flags a placeholder 'UBA (legacy alias)' that must "
                "never win. A 'banking' sector hint is enough to keep it."
            ),
        ),
        CollisionRule(
            surface="access",
            preferred="org:access-holdings-plc",
            required_hints=("ticker:ACCESSCORP", "sector:banking"),
            ambiguous_without_hint=True,
            rationale=(
                "'Access' is a common English noun ('market access', 'access to "
                "FX'). Without a banking/ticker hint we refuse to link it rather "
                "than tag every instance as Access Holdings."
            ),
        ),
        CollisionRule(
            surface="NB",
            preferred="org:nigerian-breweries-plc",
            required_hints=("ticker:NB", "sector:consumer goods"),
            ambiguous_without_hint=True,
            rationale=(
                "'NB' is also 'nota bene' in prose. Only a market/consumer-goods "
                "hint settles it."
            ),
        ),
        CollisionRule(
            surface="first bank",
            preferred="org:first-holdco-plc",
            required_hints=("sector:banking",),
            ambiguous_without_hint=False,
            rationale=(
                "Both First HoldCo and FBN Holdings match 'First Bank'; the "
                "current identity wins unless a date-scoped alias index already "
                "excluded it. There is no third 'First Bank' in the seed set."
            ),
        ),
        CollisionRule(
            surface="total",
            preferred="org:totalenergies-marketing-nigeria-plc",
            required_hints=("sector:oil and gas", "ticker:TOTAL"),
            ambiguous_without_hint=True,
            rationale=(
                "'Total' is overwhelmingly a quantifier in financial prose "
                "('total assets', 'total dividend'). Require an energy or ticker hint."
            ),
        ),
        CollisionRule(
            surface="bua",
            preferred="org:bua-cement-plc",
            required_hints=("sector:cement",),
            ambiguous_without_hint=True,
            rationale=(
                "'BUA' is the shared shorthand for BUA Cement and BUA Foods; "
                "without a sector hint we decline to choose."
            ),
        ),
        CollisionRule(
            surface="fidelity",
            preferred="org:fidelity-bank-plc",
            required_hints=("sector:banking",),
            ambiguous_without_hint=True,
            rationale="'Fidelity' also names Fidelity Investments and Fidelity International.",
        ),
        CollisionRule(
            surface="MTN Group",
            preferred="org:mtn-group-plc",
            required_hints=(),
            ambiguous_without_hint=False,
            rationale=(
                "The surface itself carries 'group': it is the JSE-listed parent, "
                "never the Nigerian subsidiary. No hint needed -- the string is "
                "already unambiguous, and it must not fuzzy-merge into MTN "
                "Nigeria (normalise_alias strips 'group', which is why this rule "
                "exists)."
            ),
        ),
        CollisionRule(
            surface="MTN Nigeria",
            preferred="org:mtn-nigeria-communications-plc",
            required_hints=(),
            ambiguous_without_hint=False,
            rationale=(
                "The surface carries 'nigeria': it is the NGX-listed subsidiary. "
                "No hint needed -- the string is already unambiguous."
            ),
        ),
        CollisionRule(
            surface="MTN",
            preferred="org:mtn-nigeria-communications-plc",
            required_hints=("ticker:MTNN", "sector:telecoms"),
            ambiguous_without_hint=True,
            rationale=(
                "Bare 'MTN' is the classic collision: the Nigerian unit's "
                "nickname, the parent's JSE code, and the telecoms sector word. "
                "In Nigerian-market text a ticker/sector hint settles it for the "
                "subsidiary; without a hint we refuse to choose (honest 'I do "
                "not know') rather than default the parent's news onto the "
                "subsidiary timeline."
            ),
        ),
    ]


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def stage_alias(
    mention: str,
    store: EntityStore,
    context: ResolutionContext,
    *,
    collisions: TickerCollisionResolver | None = None,
) -> ResolutionResult:
    """Stage 1: exact normalised alias lookup.

    Returns an ambiguous result when several distinct entities match with equal
    top confidence -- e.g. a shared acronym across two companies.
    """
    hits = store.find_by_alias(mention, reference_date=context.reference_date)
    if not hits:
        return ResolutionResult(mention_text=mention, method="none", notes="no exact alias")

    # Distinct entities only; one entity may legitimately have several aliases
    # that normalise to the same key.
    by_entity: dict[str, tuple[Entity, EntityAlias]] = {}
    for entity, alias in hits:
        by_entity.setdefault(entity.entity_id, (entity, alias))
    ranked = sorted(by_entity.values(), key=lambda p: (-p[1].confidence, p[0].entity_id))

    blocked = collisions.blocked_ids(mention) if collisions else set()
    ranked = [p for p in ranked if p[0].entity_id not in blocked] or ranked

    if len(ranked) > 1:
        top, runner = ranked[0], ranked[1]
        if top[1].confidence - runner[1].confidence <= DEFAULT_AMBIGUITY_MARGIN:
            return ResolutionResult(
                mention_text=mention,
                method="ambiguous",
                is_ambiguous=True,
                confidence=0.0,
                candidates=[(e.entity_id, a.confidence) for e, a in ranked],
                notes=(
                    f"{len(ranked)} canonical entities share this surface form with "
                    "indistinguishable confidence"
                ),
            )

    entity, alias = ranked[0]
    confidence = min(1.0, alias.confidence)
    if alias.alias_type == "ticker" and not alias.metadata.get("ticker_verified", True):
        confidence *= 0.85  # unverified ticker: exact string, uncertain meaning
    return ResolutionResult(
        mention_text=mention,
        entity_id=entity.entity_id,
        canonical_name=entity.canonical_name,
        method="alias",
        confidence=round(confidence, 4),
        matched_alias=alias.alias,
        candidates=[(e.entity_id, a.confidence) for e, a in ranked[:5]],
    )


def stage_fuzzy(
    mention: str,
    store: EntityStore,
    context: ResolutionContext,
    *,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
    collisions: TickerCollisionResolver | None = None,
) -> ResolutionResult:
    """Stage 2: fuzzy match over normalised alias surfaces using ``rapidfuzz``.

    ``WRatio`` and ``token_set_ratio`` are both computed and the **minimum** is
    taken: ``WRatio`` is generous with partial strings and would link ``"Cem"``
    to ``"cement"`` sector labels via a single shared token, while
    ``token_set_ratio`` catches word-order variation. Requiring both to clear the
    bar is the conservative choice that matches our precision-first stance.
    """
    try:  # rapidfuzz is a declared dependency, but keep the import defensive
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - only on a broken install
        return ResolutionResult(mention_text=mention, method="none", notes="rapidfuzz unavailable")

    key = normalise_alias(mention)
    if not key:
        return ResolutionResult(mention_text=mention, method="none")

    blocked = collisions.blocked_ids(mention) if collisions else set()
    fkey = fuzzy_key(mention)
    best: dict[str, tuple[float, EntityAlias]] = {}
    for surface, alias in store.all_surface_forms():
        entity = store.get(alias.entity_id)
        if entity is None or entity.entity_id in blocked:
            continue
        if not alias.is_active_on(context.reference_date):
            continue
        wratio = fuzz.WRatio(key, surface)
        tset = fuzz.token_set_ratio(fkey, fuzzy_key(alias.alias))
        score = min(float(wratio), float(tset))
        prior = best.get(alias.entity_id)
        if prior is None or score > prior[0]:
            best[alias.entity_id] = (score, alias)

    if not best:
        return ResolutionResult(mention_text=mention, method="none", notes="no candidates")

    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_id, (top_score, top_alias) = ranked[0]
    if top_score < threshold:
        return ResolutionResult(
            mention_text=mention,
            method="ambiguous" if top_score >= threshold * 0.75 else "none",
            is_ambiguous=top_score >= threshold * 0.75,
            confidence=0.0,
            candidates=[(eid, round(s, 2)) for eid, (s, _) in ranked[:5]],
            notes=f"best fuzzy score {top_score:.1f} < threshold {threshold:.1f}",
        )

    if len(ranked) > 1:
        runner_score = ranked[1][1][0]
        if top_score - runner_score < threshold * 0.03:
            return ResolutionResult(
                mention_text=mention,
                method="ambiguous",
                is_ambiguous=True,
                confidence=0.0,
                candidates=[(eid, round(s, 2)) for eid, (s, _) in ranked[:5]],
                notes="two candidates effectively tied on fuzzy score",
            )

    entity = store.get(top_id)
    # Scale the fuzzy score into a confidence and apply the stage discount.
    raw = min(1.0, top_score / 100.0)
    confidence = raw * STAGE_WEIGHTS["fuzzy"]
    return ResolutionResult(
        mention_text=mention,
        entity_id=top_id,
        canonical_name=entity.canonical_name if entity else None,
        method="fuzzy",
        confidence=round(confidence, 4),
        matched_alias=top_alias.alias,
        candidates=[(eid, round(s, 2)) for eid, (s, _) in ranked[:5]],
    )


def stage_embedding(
    mention: str,
    store: EntityStore,
    context: ResolutionContext,
    *,
    embedder: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
    threshold: float = 0.55,
) -> ResolutionResult:
    """Stage 3 (opt-in): embedding similarity.

    There is **no hard dependency** on a model here. The caller injects an
    ``embedder`` that maps a batch of strings to vectors; we do the cosine maths
    with numpy. Without an embedder the stage is a no-op returning ``none``, so
    the cascade degrades cleanly on a machine with no sentence-transformers
    install.
    """
    if embedder is None:
        return ResolutionResult(mention_text=mention, method="none", notes="no embedder injected")

    surfaces = store.all_surface_forms()
    if not surfaces:
        return ResolutionResult(mention_text=mention, method="none")

    labels = [alias.alias for _, alias in surfaces]
    entity_ids = [alias.entity_id for _, alias in surfaces]
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        return ResolutionResult(mention_text=mention, method="none", notes="numpy unavailable")

    try:
        vectors = np.asarray(embedder([mention, *labels]), dtype=float)
    except Exception as exc:  # noqa: BLE001 - a broken embedder must not kill the pipeline
        return ResolutionResult(
            mention_text=mention, method="none", notes=f"embedder failed: {exc!r}"
        )
    if vectors.ndim != 2 or vectors.shape[0] != len(labels) + 1:
        return ResolutionResult(
            mention_text=mention, method="none", notes="embedder returned wrong shape"
        )

    query = vectors[0]
    matrix = vectors[1:]
    qn = np.linalg.norm(query)
    mn = np.linalg.norm(matrix, axis=1)
    denom = np.where((mn * qn) == 0, 1e-9, mn * qn)
    sims = (matrix @ query) / denom

    best: dict[str, float] = {}
    order = np.argsort(-sims)
    for idx in order[:5]:
        eid = entity_ids[int(idx)]
        score = float(sims[int(idx)])
        if score > best.get(eid, -1.0):
            best[eid] = score
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    top_id, top_sim = ranked[0]
    if top_sim < threshold:
        return ResolutionResult(
            mention_text=mention,
            method="none",
            confidence=0.0,
            candidates=[(eid, round(s, 4)) for eid, s in ranked],
            notes=f"best cosine {top_sim:.3f} < {threshold}",
        )
    entity = store.get(top_id)
    return ResolutionResult(
        mention_text=mention,
        entity_id=top_id,
        canonical_name=entity.canonical_name if entity else None,
        method="embedding",
        confidence=round(top_sim * STAGE_WEIGHTS["embedding"], 4),
        candidates=[(eid, round(s, 4)) for eid, s in ranked],
    )


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

class EntityResolver:
    """Staged resolver implementing the pipeline ``EntityResolver`` Protocol.

    Protocol shape is ``resolve(mentions)``; the richer, documented entry point
    is :meth:`resolve_mentions`, which takes a context. ``resolve`` simply calls
    it with an empty context, so the class satisfies the Protocol *and* is
    usable directly by experiment E5 with contexts attached.
    """

    name = "staged-entity-resolver"
    version = "1.0"
    task = "entity_resolution"
    calibrated = False

    def __init__(
        self,
        store: EntityStore | None = None,
        *,
        embedder: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
        collisions: TickerCollisionResolver | None = None,
        fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
        use_embedding: bool = True,
        context_hook: Callable[[str, ResolutionContext], ResolutionResult | None] | None = None,
    ) -> None:
        self.store = store if store is not None else EntityStore.with_seed()
        self.embedder = embedder
        self.collisions = collisions if collisions is not None else TickerCollisionResolver()
        self.fuzzy_threshold = fuzzy_threshold
        self.min_confidence = min_confidence
        self.ambiguity_margin = ambiguity_margin
        self.use_embedding = use_embedding
        # Injectable so experiment E5 can ablate the context stage (pass None).
        self.context_hook = context_hook if context_hook is not None else self._context_stage

    # -- Protocol entry point -------------------------------------------
    def resolve(self, mentions: Iterable[Any]) -> list[EntityPrediction]:
        """``resolve(mentions)`` as promised to ``AnalysisPipeline``.

        Accepts ``EntitySpan`` objects (the pipeline passes NER output) or plain
        dicts with ``text``/``start``/``end``/``entity_type``.
        """
        context = ResolutionContext(reference_date=None)
        return self.resolve_mentions(mentions, context)

    # -- rich entry point ------------------------------------------------
    def resolve_mentions(
        self,
        mentions: Iterable[Any],
        context: ResolutionContext | dict[str, Any] | None = None,
    ) -> list[EntityPrediction]:
        """Resolve mentions to :class:`EntityPrediction`, preserving span offsets.

        ``mentions`` are ``EntitySpan`` objects or compatible dicts.
        ``context`` is a :class:`ResolutionContext` or a plain dict (so callers
        can pass ``{"tickers": ["DANGCEM"], "publisher": "businessday"}``).
        """
        ctx = _coerce_context(context)
        predictions: list[EntityPrediction] = []
        for mention in mentions:
            span = _coerce_span(mention)
            if span is None:
                continue
            result = self.resolve_one(span.text, ctx)
            predictions.append(self._to_prediction(span, result, ctx))
        return predictions

    def resolve_one(self, mention: str, context: ResolutionContext | None = None) -> ResolutionResult:
        """Run the full cascade for a single mention surface form."""
        ctx = context or ResolutionContext()
        text = (mention or "").strip()
        if not text:
            return ResolutionResult(mention_text=mention, method="none", notes="empty mention")

        # Collision rules first: a rule whose surface form is itself
        # unambiguous ("MTN Group") can settle the mention outright, while a
        # hint-dependent rule ("MTN") either resolves with context or refuses.
        preferred = self.collisions.preferred_with_hints(text, ctx)
        if preferred and self.store.get(preferred) is not None:
            entity = self.store.get(preferred)
            return ResolutionResult(
                mention_text=text,
                entity_id=preferred,
                canonical_name=entity.canonical_name if entity else None,
                method="context",
                confidence=0.9,
                notes=(
                    "collision rule satisfied by surface form / context hints"
                ),
            )
        if self.collisions.is_genuinely_ambiguous(text, ctx):
            return ResolutionResult(
                mention_text=text,
                method="ambiguous",
                is_ambiguous=True,
                confidence=0.0,
                notes="collision rule: context cannot disambiguate this surface form",
            )

        # Stage 1: context hook may settle it outright (ticker co-occurrence).
        hooked = self.context_hook(text, ctx) if self.context_hook else None
        if hooked is not None and hooked.resolved:
            return hooked

        # Stage 2: exact alias.
        result = stage_alias(text, self.store, ctx, collisions=self.collisions)
        if result.resolved and result.confidence >= self.min_confidence:
            return result
        if result.is_ambiguous:
            return result

        # Stage 3: fuzzy.
        fuzzy = stage_fuzzy(
            text,
            self.store,
            ctx,
            threshold=self.fuzzy_threshold,
            collisions=self.collisions,
        )
        if fuzzy.resolved and fuzzy.confidence >= self.min_confidence:
            return fuzzy
        if fuzzy.is_ambiguous and not result.resolved:
            return fuzzy

        # Stage 4: embedding (only when explicitly injected).
        if self.use_embedding and self.embedder is not None:
            embedded = stage_embedding(text, self.store, ctx, embedder=self.embedder)
            if embedded.resolved and embedded.confidence >= self.min_confidence:
                return embedded
            if embedded.resolved:
                return embedded

        # Nothing cleared the bar: prefer the explicit "ambiguous" outcome over a
        # low-confidence wrong link.
        best = fuzzy if fuzzy.candidates else result
        if best.candidates:
            return ResolutionResult(
                mention_text=text,
                method="ambiguous",
                is_ambiguous=True,
                confidence=0.0,
                candidates=best.candidates,
                notes="no stage cleared the confidence threshold",
            )
        return ResolutionResult(mention_text=text, method="none", notes="no candidate found")

    # -- context stage ---------------------------------------------------
    def _context_stage(self, mention: str, context: ResolutionContext) -> ResolutionResult | None:
        """Promote a candidate when a co-occurring ticker pins the mention down.

        The rule is narrow on purpose: we only fire when the mention itself is
        *not* already an exact alias (otherwise stage 1/2 would be more
        trustworthy) and a ticker elsewhere in the document resolves to exactly
        one entity that also has this mention as a weak (fuzzy) candidate.
        """
        key = normalise_alias(mention)
        if not key or not context.tickers:
            return None
        # Only act on mentions that are *not* exact aliases.
        if self.store.find_by_alias(mention, reference_date=context.reference_date):
            return None

        ticker_entities: list[Entity] = []
        for ticker in context.tickers:
            ticker_entities.extend(self.store.find_by_ticker(ticker))
        ticker_ids = {e.entity_id for e in ticker_entities}
        if len(ticker_ids) != 1:
            return None

        # Sector agreement is a second, independent signal.
        candidate_id = next(iter(ticker_ids))
        entity = self.store.get(candidate_id)
        if entity is None:
            return None
        if context.sectors and entity.sectors:
            if not {s.lower() for s in entity.sectors} & {s.lower() for s in context.sectors}:
                return None
        # Require some string evidence linking mention to the entity, so a stray
        # ticker cannot drag every mention in the document onto one company.
        if not _weakly_related(key, entity, self.store):
            return None
        return ResolutionResult(
            mention_text=mention,
            entity_id=entity.entity_id,
            canonical_name=entity.canonical_name,
            method="context",
            confidence=0.86,
            notes=f"co-occurring ticker {sorted(context.tickers)}",
        )

    # -- helpers ---------------------------------------------------------
    def _to_prediction(
        self, span: EntitySpan, result: ResolutionResult, context: ResolutionContext
    ) -> EntityPrediction:
        return EntityPrediction(
            span=span,
            entity_id=result.entity_id,
            canonical_name=result.canonical_name,
            resolution_method=result.method,
            confidence=result.confidence,
        )


def _weakly_related(key: str, entity: Entity, store: EntityStore) -> bool:
    """Cheap lexical overlap test between a mention key and an entity's aliases."""
    entity_keys = {normalise_alias(a.alias) for a in store.aliases_for(entity.entity_id)}
    entity_keys |= {normalise_alias(entity.canonical_name)}
    mention_tokens = set(key.split())
    for candidate in entity_keys:
        if not candidate:
            continue
        if key in candidate or candidate in key:
            return True
        if mention_tokens & set(candidate.split()):
            return True
    return False


def _coerce_context(context: ResolutionContext | dict[str, Any] | None) -> ResolutionContext:
    if context is None:
        return ResolutionContext()
    if isinstance(context, ResolutionContext):
        return context
    if isinstance(context, dict):
        known = {
            "text", "tickers", "sectors", "country", "publisher", "reference_date",
        }
        payload = {k: v for k, v in context.items() if k in known}
        extras = {k: v for k, v in context.items() if k not in known}
        if "tickers" in payload and payload["tickers"] is not None:
            payload["tickers"] = tuple(payload["tickers"])
        if "sectors" in payload and payload["sectors"] is not None:
            payload["sectors"] = tuple(payload["sectors"])
        ref = payload.get("reference_date")
        if isinstance(ref, str) and ref:
            try:
                payload["reference_date"] = date.fromisoformat(ref)
            except ValueError:
                payload["reference_date"] = None
        payload["extra"] = extras
        return ResolutionContext(**payload)
    raise TypeError(f"unsupported context type: {type(context)!r}")


def _coerce_span(mention: Any) -> EntitySpan | None:
    """Accept an ``EntitySpan``, an ``EntityPrediction`` (pipeline output), or a
    dict/tuple-shaped mention.

    The pipeline passes NER predictions straight into ``resolve``; rejecting
    them here meant ``resolve`` silently returned an empty list and the whole
    product shipped with zero entity data.
    """
    if isinstance(mention, EntityPrediction):
        return mention.span
    if isinstance(mention, EntitySpan):
        return mention
    if isinstance(mention, dict):
        text = str(mention.get("text", ""))
        start = int(mention.get("start", 0))
        end = int(mention.get("end", start + len(text)))
        raw_type = mention.get("entity_type", "ORG")
        try:
            etype = EntityType(raw_type)
        except ValueError:
            etype = EntityType.ORG
        if end <= start:
            end = start + max(1, len(text))
        return EntitySpan(start=start, end=end, text=text, entity_type=etype)
    return None


_TICKER_RE = re.compile(r"\b[A-Z]{2,12}\b")


def tickers_in_text(text: str, store: EntityStore) -> list[str]:
    """Find tickers that appear literally in ``text`` (context builder helper).

    Only tickers the store actually knows are returned, so this never invents a
    hint that then silently drives a resolution.
    """
    known = {t.upper() for e in store.all_entities() for t in e.tickers}
    found: list[str] = []
    for match in _TICKER_RE.finditer(text or ""):
        token = match.group(0).upper()
        if token in known and token not in found:
            found.append(token)
    return found
