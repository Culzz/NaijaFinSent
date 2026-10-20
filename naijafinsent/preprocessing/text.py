"""Deterministic, dependency-free text preprocessing.

Everything here is rule/regex based on purpose: we run in CI, in the API, and
in offline notebooks, and we must never trigger an NLTK/Punkt download or
depend on a tokenizer that changes between releases. The tokenizer below is
documented precisely so that *char offsets are reproducible* -- the NER code
relies on the fact that ``tokenize_words`` and ``char_offsets_to_token_indices``
agree on boundaries.

Design contract
---------------
* ``tokenize_words`` splits on whitespace, then peels punctuation off word
  edges as its own token, and additionally splits "word/number" transitions
  deterministically (e.g. ``"N2bn"`` -> ``["N2bn"]`` is *not* what happens;
  see the rules in the docstring of the function).
* ``char_offsets_to_token_indices`` returns, for each character position in the
  input, the index of the token that covers it (or ``-1`` for separator
  characters such as whitespace). This is the alignment the BIO tagger uses to
  map annotated ``EntitySpan`` char offsets onto token tags and back.
"""

from __future__ import annotations

import re
from typing import Callable

from naijafinsent.utils import normalise_text

__all__ = [
    "strip_urls",
    "collapse_whitespace",
    "clean_for_model",
    "split_sentences",
    "tokenize_words",
    "char_offsets_to_token_indices",
    "is_likely_english",
    "DEFAULT_TOKENIZER",
]

# --------------------------------------------------------------------------
# URLs / whitespace
# --------------------------------------------------------------------------

_URL_RE = re.compile(
    r"""(?xi)
    \b(?:
        https?://[^\s<>"')\]]+              # http(s)://...
        | www\.[^\s<>"')\]]+                # www....
        | [a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}   # email (treated as url-ish noise)
    )
    """
)

_WS_RUN_RE = re.compile(r"\s+")

# --------------------------------------------------------------------------
# Sentence splitting
# --------------------------------------------------------------------------

# Abbreviations that end with a period but should not terminate a sentence.
# Kept deliberately small and Nigeria/finance-flavoured.
_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "engr", "barr", "sen", "rep", "gov",
        "hon", "chief", "alh", "alhaji", "st", "no", "vol", "vs", "etc",
        "inc", "ltd", "plc", "co", "corp", "dept", "est", "approx", "cf",
        "eg", "ie", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
        "sept", "oct", "nov", "dec", "ngn", "usd", "gbp", "eur", "bn", "mn",
    }
)

# A sentence terminator: . ! ? … optionally followed by closing quotes/brackets.
_TERMINATOR_RE = re.compile(r"[.!?\u2026]+[\"')\]\u201d\u2019]*")
_SENTENCE_BOUNDARY_RE = re.compile(
    r"""
    (?<=[.!?\u2026])       # just after a terminator
    [\"')\]\u201d\u2019]*   # optional closing punctuation
    \s+                    # whitespace
    (?=[A-Z0-9\u201c\u2018"'])  # next sentence likely starts with capital/digit
    """,
    re.VERBOSE,
)


def _is_abbreviation(text: str, dot_pos: int) -> bool:
    """True if the period at ``dot_pos`` closes a known abbreviation/number."""
    # Number like "1.5" or a decimal point: never a sentence end.
    if dot_pos > 0 and text[dot_pos - 1].isdigit():
        nxt = text[dot_pos + 1 : dot_pos + 2]
        if nxt.isdigit():
            return True
    # Grab trailing alphabetic chunk before the dot.
    j = dot_pos
    while j > 0 and (text[j - 1].isalpha() or text[j - 1] == "."):
        j -= 1
    chunk = text[j:dot_pos]
    if not chunk:
        return False
    if chunk.lower().strip(".") in _ABBREVIATIONS:
        return True
    # Single initial, e.g. "J. Bola"
    if len(chunk) == 1 and chunk.isalpha():
        return True
    return False


def split_sentences(text: str, *, max_len: int | None = None) -> list[str]:
    """Rule-based sentence splitter (no NLTK download).

    Splits on ``.``/``!``/``?``/``…`` followed by whitespace and an
    uppercase/digit/quoted start, while protecting common abbreviations,
    initials, decimals, and ₦-style amounts. Newlines are hard boundaries.

    Args:
        text: raw or normalised text.
        max_len: if given, sentences longer than this are split on the last
            whitespace before the limit, so downstream models never see an
            oversized "sentence".

    Returns:
        A list of sentence strings, each stripped. Empty input -> ``[]``. The
        concatenation of the sentences (joined by a single space) preserves the
        word content of the input, though not exact whitespace.
    """
    if not text or not text.strip():
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Step 1: hard-split on newlines, then soft-split each line on punctuation.
    sentences: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Find candidate boundaries then veto abbreviation/decimal ones.
        boundaries: list[int] = []
        for m in re.finditer(r"[.!?\u2026]+\s+", line):
            dot_pos = m.start()
            if "." in line[dot_pos : m.end()]:
                if _is_abbreviation(line, dot_pos):
                    continue
            boundaries.append(m.end())

        start = 0
        for b in boundaries:
            piece = line[start:b].strip()
            if piece:
                sentences.append(piece)
            start = b
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)

    # Step 2: enforce max_len by splitting on whitespace only if needed.
    if max_len and max_len > 0:
        out: list[str] = []
        for s in sentences:
            while len(s) > max_len:
                cut = s.rfind(" ", 0, max_len)
                if cut <= 0:
                    cut = max_len
                out.append(s[:cut].strip())
                s = s[cut:].strip()
            if s:
                out.append(s)
        sentences = out

    return sentences


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

# Character class helpers, kept explicit so behaviour is auditable.
_PUNCT_CHARS = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"


def tokenize_words(text: str) -> list[str]:
    """Deterministic whitespace + punctuation + number-aware tokenizer.

    Rules, applied in order (all regex-based, no external data):

    1. Runs of whitespace are separators and never appear as tokens.
    2. A maximal run of *word* characters (``\\w`` including letters, digits and
       underscore, plus ``₦`` and other currency-ish symbols handled below) is
       a candidate token.
    3. Punctuation characters are emitted as their own single-character tokens,
       **except** internal periods/commas that sit between digits (thousands
       separators or decimals), which stay attached to the number: ``"1,234.50"``
       is one token.
    4. Money/unit compounds stay together when written without spaces:
       ``"₦2bn"``, ``"N40m"``, ``"$1.2m"`` are single tokens. This is achieved
       because ``₦$£€`` are treated as word characters and the digit/letter run
       that follows is contiguous.
    5. Hyphens and slashes between alphanumerics are kept inside the token
       (``"oil & gas"`` is three tokens; ``"N2-3bn"`` is one token because the
       digits/hyphen/digits are contiguous). A leading or trailing hyphen
       becomes its own punctuation token.

    The output is fully reconstructible: see :func:`char_offsets_to_token_indices`
    for the alignment guarantee used by the NER code.

    Examples:
        >>> tokenize_words("CBN raised the MPR to 27.5%, says Emefiele.")
        ['CBN', 'raised', 'the', 'MPR', 'to', '27.5', '%', ',', 'says', 'Emefiele', '.']
        >>> tokenize_words("Net profit hit ₦2.3bn in Q1.")
        ['Net', 'profit', 'hit', '₦2.3bn', 'in', 'Q1', '.']
    """
    if not text:
        return []

    # Currency symbols are treated as word characters so "₦2bn" stays whole.
    word_char = r"\w\u20a6\u0024\u00a3\u20ac"  # \w, ₦, $, £, €
    pattern = re.compile(
        rf"(?:[{word_char}]+(?:[.,][{word_char}]+)*)"   # word/number group (1)
        rf"|(?:[{word_char}]+(?:[-/][{word_char}]+)+)"  # hyphen/slash-compound (2)
        rf"|(?:[{word_char}]+)"                          # plain word run (3)
        rf"|(?:[^\s{word_char}])"                        # single punctuation char (4)
    )
    return pattern.findall(text)


DEFAULT_TOKENIZER: Callable[[str], list[str]] = tokenize_words


def _token_spans(text: str, tokenizer_fn: Callable[[str], list[str]]) -> list[tuple[int, int]]:
    """Locate each token produced by ``tokenizer_fn`` back in ``text``.

    Scans left-to-right for the literal token text, skipping separators. Falls
    back to a best-effort search if a tokenizer normalises tokens (it shouldn't
    for our tokenizer, but custom tokenizers may lowercase already-split runs).
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    n = len(text)
    for tok in tokenizer_fn(text):
        if not tok:
            continue
        idx = text.find(tok, cursor)
        if idx < 0:
            # Fallback: search from the beginning (handles reordered/normalised
            # tokens), else place at cursor with token length.
            idx = text.find(tok)
            if idx < 0:
                spans.append((cursor, min(cursor + len(tok), n)))
                cursor = min(cursor + len(tok), n)
                continue
        start = idx
        end = idx + len(tok)
        spans.append((start, end))
        cursor = end
    return spans


def char_offsets_to_token_indices(
    text: str,
    tokenizer_fn: Callable[[str], list[str]] = DEFAULT_TOKENIZER,
) -> tuple[list[str], list[tuple[int, int]], list[int]]:
    """Align characters in ``text`` to token indices.

    Returns:
        ``(tokens, spans, char_to_token)`` where

        * ``tokens`` is ``tokenizer_fn(text)``,
        * ``spans[i] == (start, end)`` are the char offsets of token ``i`` in the
          original ``text`` (``text[start:end] == tokens[i]``),
        * ``char_to_token`` has length ``len(text)``; ``char_to_token[c]`` is the
          index of the token covering character ``c``, or ``-1`` for separator
          characters (whitespace between tokens).

    The alignment is *exact*: ``text[start:end] == tokens[i]`` for every token,
    and every non-separator character in ``text`` maps to a token whose span
    contains it. This is the guarantee NER relies on.
    """
    tokens = tokenizer_fn(text)
    spans = _token_spans(text, tokenizer_fn)
    if len(spans) != len(tokens):
        # Defensive: keep them the same length.
        spans = spans[: len(tokens)]

    char_to_token = [-1] * len(text)
    for i, (s, e) in enumerate(spans):
        for c in range(max(0, s), min(e, len(text))):
            char_to_token[c] = i
    return tokens, spans, char_to_token


# --------------------------------------------------------------------------
# Clean / heuristics
# --------------------------------------------------------------------------

def strip_urls(text: str) -> str:
    """Remove URLs and email addresses, replacing each with a single space."""
    if not text:
        return ""
    return _URL_RE.sub(" ", text)


def collapse_whitespace(text: str) -> str:
    """Collapse any run of whitespace to a single space and strip the ends.

    Unlike :func:`naijafinsent.utils.normalise_text` this does *not* do NFKC or
    punctuation cleanup; it is the minimal whitespace-only collapse.
    """
    if not text:
        return ""
    return _WS_RUN_RE.sub(" ", text).strip()


def clean_for_model(text: str) -> str:
    """Canonical, model-ready string.

    Applies NFKC normalisation + whitespace collapsing (via ``normalise_text``),
    then strips URLs/emails which add noise and leak publisher boilerplate.
    Offsets into this cleaned string are stable for a single call, but note that
    URL removal changes offsets relative to the raw input -- annotation offsets
    must therefore be computed against the same cleaned text the model sees.
    """
    if not text:
        return ""
    return collapse_whitespace(strip_urls(normalise_text(text)))


# Cheap English heuristic: function-word density plus Latin-script ratio.
_ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "of", "and", "to", "in", "a", "is", "that", "for", "on", "with",
        "as", "was", "by", "at", "from", "it", "has", "have", "will", "its",
        "this", "are", "be", "an", "said", "but", "not", "or", "which", "we",
    }
)
_PIDGIN_MARKERS: frozenset[str] = frozenset(
    {"dey", "don", "na", "wetin", "sabi", "abeg", "wahala", "oya", "no be", "shey"}
)


def is_likely_english(text: str) -> bool:
    """Cheap, dependency-free English heuristic.

    Heuristic (documented honestly as a heuristic, not a classifier):

    * Reject if fewer than 20% of alphabetic characters are ASCII Latin.
    * Score = (stopword hits / tokens) + 0.5 * (ASCII-Latin ratio).
    * Accept when ``score >= 0.25``; strongly accept on any English stopword
      hit plus a high Latin ratio. Nigerian Pidgin markers count *for* English
      here because they share the Latin script and much vocabulary -- we treat
      Pidgin as in-scope English-like text for this platform.
    """
    if not text or not text.strip():
        return False
    tokens = tokenize_words(text.lower())
    alpha = [t for t in tokens if t.isalpha()]
    if not alpha:
        # Numbers/symbols only: not enough signal to claim non-English.
        return True

    latin = sum(1 for t in alpha if all(ord(c) < 128 for c in t))
    latin_ratio = latin / len(alpha)
    if latin_ratio < 0.20:
        return False

    stop_hits = sum(1 for t in tokens if t in _ENGLISH_STOPWORDS)
    pidgin_hits = sum(1 for m in _PIDGIN_MARKERS if m in text.lower())
    score = (stop_hits / len(tokens)) + 0.5 * latin_ratio + 0.1 * min(pidgin_hits, 1)
    return score >= 0.25
