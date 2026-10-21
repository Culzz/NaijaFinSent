"""Offset-safe BIO tagging utilities.

The core problem: annotations are given as character spans, but taggers consume
token sequences, and transformer tokenizers further split words into subwords.
These helpers must round-trip exactly: ``bio_to_spans(text, *spans_to_bio(...))``
must return the original spans.

Subword scheme (documented):
    * ``spans_to_bio`` consumes the *word* tokenizer's tokens (from
      ``preprocessing.text.tokenize_words``) and char spans, and emits one tag
      per word token.
    * For subword tokenizers, ``spans_to_bio_subwords`` emits ``B-`` on the
      first subword of a mention and ``I-`` on continuation subwords, and ``O``
      elsewhere. Only the *first* subword's start offset and the *last*
      subword's end offset are used to reconstruct the span, so continuation
      pieces are handled by merging adjacent same-type ``B``/``I`` runs.
"""

from __future__ import annotations

from typing import Callable, Sequence

from naijafinsent.schemas import EntitySpan, EntityType
from naijafinsent.ner.base import BIO

__all__ = [
    "spans_to_bio",
    "bio_to_spans",
    "token_offsets",
    "spans_to_bio_subwords",
]


def token_offsets(
    text: str,
    tokenizer_fn: Callable[[str], list[str]],
) -> list[tuple[int, int]]:
    """Character offsets of each token produced by ``tokenizer_fn`` in ``text``.

    Guarantees ``text[start:end] == tokens[i]`` for every token, by scanning
    left-to-right for each token's literal text (skipping separators). Tokens
    that cannot be found are given a zero-width span at the cursor so lengths
    stay aligned; this should not happen for our whitespace tokenizer.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    n = len(text)
    for tok in tokenizer_fn(text):
        idx = text.find(tok, cursor) if tok else -1
        if idx < 0:
            idx = text.find(tok) if tok else -1
        if idx < 0:
            spans.append((cursor, cursor))
            continue
        spans.append((idx, idx + len(tok)))
        cursor = idx + len(tok)
        if cursor > n:
            cursor = n
    return spans


def spans_to_bio(
    text: str,
    spans: Sequence[EntitySpan],
    tokenizer_fn: Callable[[str], list[str]],
) -> tuple[list[str], list[str]]:
    """Convert char-span annotations into word-level BIO tags.

    Returns ``(tokens, tags)`` where ``tokens == tokenizer_fn(text)`` and
    ``len(tags) == len(tokens)``.

    A token is tagged ``B-TYPE`` if it *starts* inside a span, and ``I-TYPE`` if
    it is a continuation token fully inside the same span. A token that merely
    touches a span boundary without being contained is ``O``. Overlapping spans
    are resolved left-to-right, first-wins (annotations should not overlap).
    """
    tokens = tokenizer_fn(text)
    offsets = token_offsets(text, tokenizer_fn)
    tags = [BIO.O] * len(tokens)

    # Sort spans left-to-right; first-wins on overlap.
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    assigned = [False] * len(tokens)

    for span in ordered:
        et = span.entity_type.value if isinstance(span.entity_type, EntityType) else str(span.entity_type)
        first = True
        for i, (ts, te) in enumerate(offsets):
            if ts >= span.end or te <= span.start:
                continue  # no overlap with this span
            if assigned[i]:
                continue
            # Token is (partially) inside the span.
            if first:
                tags[i] = BIO.begin(et)
                first = False
            else:
                tags[i] = BIO.inside(et)
            assigned[i] = True

    return tokens, tags


def bio_to_spans(
    text: str,
    tokens: Sequence[str],
    tags: Sequence[str],
    offsets: Sequence[tuple[int, int]] | None = None,
    tokenizer_fn: Callable[[str], list[str]] | None = None,
) -> list[EntitySpan]:
    """Convert word-level BIO tags back into char-offset ``EntitySpan`` objects.

    Args:
        text: the source text.
        tokens: the token sequence (must match the original tokenization).
        tags: BIO tags, same length as ``tokens``.
        offsets: optional precomputed char offsets; if omitted, they are derived
            by locating each token in ``text`` sequentially.
        tokenizer_fn: unused when ``offsets`` is given; kept for API symmetry.

    A ``B-`` tag opens a span; following ``I-`` tags of the *same type* extend
    it. An ``I-`` tag of a different type also opens a new span (defensive
    against malformed tag sequences). Span start is the first token's start,
    span end is the last token's end, so the reconstructed span text equals the
    original surface form.
    """
    if not tokens:
        return []
    if len(tags) != len(tokens):
        raise ValueError(f"tokens/tags length mismatch: {len(tokens)} vs {len(tags)}")

    if offsets is None:
        if tokenizer_fn is None:
            from naijafinsent.preprocessing.text import tokenize_words as tokenizer_fn  # type: ignore
        offsets = token_offsets(text, tokenizer_fn)

    spans: list[EntitySpan] = []
    cur_type: str | None = None
    cur_start: int | None = None
    cur_end: int | None = None

    def flush() -> None:
        nonlocal cur_type, cur_start, cur_end
        if cur_type is not None and cur_start is not None and cur_end is not None:
            spans.append(
                EntitySpan(
                    start=cur_start,
                    end=cur_end,
                    text=text[cur_start:cur_end],
                    entity_type=EntityType(cur_type),
                )
            )
        cur_type, cur_start, cur_end = None, None, None

    for i, tag in enumerate(tags):
        prefix, et = BIO.parse(tag)
        ts, te = offsets[i]
        if prefix == "B" and et is not None:
            flush()
            cur_type, cur_start, cur_end = et, ts, te
        elif prefix == "I" and et is not None:
            if cur_type == et and cur_start is not None:
                cur_end = te
            else:
                # Malformed continuation: start a new span of this type.
                flush()
                cur_type, cur_start, cur_end = et, ts, te
        else:
            flush()
    flush()
    return spans


def spans_to_bio_subwords(
    offsets: Sequence[tuple[int, int]],
    spans: Sequence[EntitySpan],
    *,
    special_mask: Sequence[bool] | None = None,
) -> list[str]:
    """Emit BIO tags for *subword* offsets (e.g. from ``return_offsets_mapping``).

    Args:
        offsets: ``(start, char_end)`` for each subword; ``(0, 0)`` marks
            special tokens (``[CLS]``/``[SEP]``/padding).
        spans: gold entity spans (char offsets).
        special_mask: optional booleans, True for special tokens to force ``O``.

    A subword is ``B-TYPE`` if its start >= span.start and it is the first
    subword overlapping the span; subsequent overlapping subwords are ``I-TYPE``.
    Special tokens always get ``O``.
    """
    tags = [BIO.O] * len(offsets)
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    first_seen: dict[int, bool] = {}
    for span_idx, span in enumerate(ordered):
        et = span.entity_type.value if isinstance(span.entity_type, EntityType) else str(span.entity_type)
        first_seen[span_idx] = True
        for i, (ts, te) in enumerate(offsets):
            if special_mask is not None and special_mask[i]:
                continue
            if ts == te == 0:
                continue
            if ts >= span.end or te <= span.start:
                continue
            if tags[i] != BIO.O:
                continue
            if first_seen[span_idx]:
                tags[i] = BIO.begin(et)
                first_seen[span_idx] = False
            else:
                tags[i] = BIO.inside(et)
    return tags
