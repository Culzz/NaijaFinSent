"""CRF NER via ``sklearn_crfsuite``.

``sklearn_crfsuite`` is **not** in ``pyproject.toml`` yet (it wraps the C
``crfsuite`` library). The import is therefore guarded: constructing
:class:`CrfNer` works with base deps installed, but calling :meth:`fit` or
:meth:`predict` raises a clear, actionable error telling you how to install it.

Features per token (word shape, affixes, casing, digits, neighbours, lexicon
flags, BOS/EOS) follow the standard CoNLL-style CRF recipe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from naijafinsent.preprocessing.lexicon import Lexicon
from naijafinsent.preprocessing.text import tokenize_words
from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType
from naijafinsent.ner.base import BIO, BaseNerModel
from naijafinsent.ner.bio import spans_to_bio, token_offsets

__all__ = ["CrfNer", "word2features", "MISSING_CRF_MSG"]

MISSING_CRF_MSG = (
    "CrfNer requires 'sklearn_crfsuite' (which needs the python-crfsuite C "
    "extension). Install it with: pip install python-crfsuite sklearn-crfsuite. "
    "It is intentionally excluded from the base install because it needs a "
    "compiler. The rule-based NER works without it."
)


def _require_crfsuite():
    try:
        import sklearn_crfsuite  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(MISSING_CRF_MSG) from exc
    import sklearn_crfsuite

    return sklearn_crfsuite


def _word_shape(word: str) -> str:
    """Collapse a word to a shape string: ``Xx``, ``DD``, ``Xx-Dd`` etc."""
    shape = []
    for ch in word:
        if ch.isupper():
            shape.append("X")
        elif ch.islower():
            shape.append("x")
        elif ch.isdigit():
            shape.append("d")
        else:
            shape.append(ch)
    # Collapse runs of identical shape chars.
    out = []
    for c in shape:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def word2features(
    tokens: Sequence[str],
    i: int,
    *,
    lexicon_surfaces: frozenset[str] = frozenset(),
    offsets: Sequence[tuple[int, int]] | None = None,
) -> dict[str, object]:
    """Feature dict for token ``i`` (CoNLL-style).

    Includes: lowercased word, word shape, prefixes/suffixes (2-4), casing flags,
    digit/hyphen/currency patterns, BOS/EOS markers, and the previous/next word
    and shape. ``lexicon_surfaces`` adds a `lex` flag when the lowercase token is
    a known entity surface.
    """
    word = tokens[i]
    lower = word.lower()

    feats: dict[str, object] = {
        "bias": 1.0,
        "word.lower": lower,
        "word.shape": _word_shape(word),
        "word.isupper": word.isupper(),
        "word.istitle": word.istitle(),
        "word.isdigit": word.isdigit(),
        "word.has_digit": any(ch.isdigit() for ch in word),
        "word.has_hyphen": "-" in word,
        "word.has_currency": any(ch in "\u20a6$£€" for ch in word),
        "word.has_punct": any(not ch.isalnum() for ch in word),
        "word.len": len(word),
        "lex": lower in lexicon_surfaces,
    }
    for n in (2, 3, 4):
        if len(word) >= n:
            feats[f"prefix{n}"] = lower[:n]
            feats[f"suffix{n}"] = lower[-n:]

    if i > 0:
        prev = tokens[i - 1]
        feats.update(
            {
                "-1:word.lower": prev.lower(),
                "-1:word.shape": _word_shape(prev),
                "-1:word.istitle": prev.istitle(),
                "-1:word.isupper": prev.isupper(),
            }
        )
    else:
        feats["BOS"] = True

    if i < len(tokens) - 1:
        nxt = tokens[i + 1]
        feats.update(
            {
                "+1:word.lower": nxt.lower(),
                "+1:word.shape": _word_shape(nxt),
                "+1:word.istitle": nxt.istitle(),
                "+1:word.isupper": nxt.isupper(),
            }
        )
    else:
        feats["EOS"] = True

    return feats


class CrfNer(BaseNerModel):
    """Linear-chain CRF sequence tagger over BIO tags."""

    name = "crf-ner"
    version = "0.1.0"
    calibrated = False

    def __init__(
        self,
        *,
        lexicon: Lexicon | None = None,
        c1: float = 0.1,
        c2: float = 0.1,
        max_iterations: int = 100,
        algorithm: str = "lbfgs",
        all_possible_transitions: bool = True,
    ) -> None:
        self.lexicon = lexicon or Lexicon.from_file()
        self.c1 = c1
        self.c2 = c2
        self.max_iterations = max_iterations
        self.algorithm = algorithm
        self.all_possible_transitions = all_possible_transitions
        self._crf = None
        self._lexicon_surfaces = frozenset(self.lexicon._index.keys())
        self._tags = BIO.all_tags()

    # -- feature extraction --------------------------------------------
    def _sent2features(self, tokens: Sequence[str]) -> list[dict[str, object]]:
        offsets = None
        return [
            word2features(tokens, i, lexicon_surfaces=self._lexicon_surfaces, offsets=offsets)
            for i in range(len(tokens))
        ]

    def _sent2labels(self, tags: Sequence[str]) -> list[str]:
        return list(tags)

    # -- training -------------------------------------------------------
    def fit(self, texts: Sequence[str], spans: Sequence[list[EntitySpan]], **kwargs) -> CrfNer:
        """Train on parallel ``(text, spans)`` lists."""
        crfsuite = _require_crfsuite()
        X, y = [], []
        for text, sent_spans in zip(texts, spans):
            tokens, tags = spans_to_bio(text, sent_spans, tokenize_words)
            X.append(self._sent2features(tokens))
            y.append(self._sent2labels(tags))
        crf = crfsuite.CRF(
            algorithm=self.algorithm,
            c1=self.c1,
            c2=self.c2,
            max_iterations=self.max_iterations,
            all_possible_transitions=self.all_possible_transitions,
        )
        crf.fit(X, y)
        self._crf = crf
        return self

    # -- inference ------------------------------------------------------
    def predict(self, text: str) -> list[EntityPrediction]:
        if self._crf is None:
            raise RuntimeError("CrfNer is not fitted; call fit() before predict().")
        tokens = tokenize_words(text)
        if not tokens:
            return []
        feats = self._sent2features(tokens)
        tags = self._crf.predict_single(feats)
        offsets = token_offsets(text, tokenize_words)
        spans = _tags_to_spans(text, tokens, tags, offsets)
        return [
            EntityPrediction(
                span=s,
                confidence=self._token_confidence(tags, s),
                resolution_method=None,
            )
            for s in spans
        ]

    @staticmethod
    def _token_confidence(tags: Sequence[str], span: EntitySpan) -> float:
        # CRF does not expose per-span probabilities here; report a fixed prior.
        return 0.75

    # -- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        if self._crf is None:
            raise RuntimeError("cannot save an unfitted CrfNer")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._crf.save(str(path))
        meta = path.with_suffix(path.suffix + ".meta.json")
        meta.write_text(
            json.dumps(
                {
                    "name": self.name,
                    "version": self.version,
                    "c1": self.c1,
                    "c2": self.c2,
                    "algorithm": self.algorithm,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> CrfNer:
        crfsuite = _require_crfsuite()
        model = cls()
        crf = crfsuite.CRF()
        crf.load(str(path))
        model._crf = crf
        return model


def _tags_to_spans(
    text: str,
    tokens: Sequence[str],
    tags: Sequence[str],
    offsets: Sequence[tuple[int, int]],
) -> list[EntitySpan]:
    """Merge a word-level BIO tag sequence into char-offset spans."""
    spans: list[EntitySpan] = []
    cur_type: str | None = None
    start: int | None = None
    end: int | None = None

    def flush() -> None:
        nonlocal cur_type, start, end
        if cur_type is not None and start is not None and end is not None:
            spans.append(
                EntitySpan(
                    start=start, end=end, text=text[start:end],
                    entity_type=EntityType(cur_type),
                )
            )
        cur_type, start, end = None, None, None

    for i, tag in enumerate(tags):
        prefix, et = BIO.parse(tag)
        ts, te = offsets[i]
        if prefix == "B" and et is not None:
            flush()
            cur_type, start, end = et, ts, te
        elif prefix == "I" and et is not None and cur_type == et:
            end = te
        else:
            flush()
    flush()
    return spans
