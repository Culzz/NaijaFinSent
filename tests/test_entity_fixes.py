"""Regression locks for the two silent-failure entity bugs (chunk 2).

* Bug A — ``Lexicon.from_file`` looked for an ``entities``/``entries`` key but
  the committed lexicon uses ``terms``, so the reviewed 88-entry lexicon file
  was never loaded; everything silently ran on the 36-entry embedded fallback.
* Bug B — ``_coerce_span`` rejected ``EntityPrediction`` (exactly what the
  pipeline feeds the resolver), so ``resolve`` returned an empty list and the
  whole product shipped zero resolved entities.
* MTN collision — "MTN Group" / "MTN Nigeria" / bare "MTN" must be three
  different decisions: parent, subsidiary, honest-ambiguous.
"""

from __future__ import annotations

from naijafinsent.inference.pipeline import StubPipeline
from naijafinsent.ner.rules import RuleBasedNer
from naijafinsent.preprocessing.lexicon import load_default_lexicon


def test_committed_lexicon_is_actually_loaded_not_the_fallback():
    lex = load_default_lexicon()
    assert lex.source is not None and lex.source.endswith("lexicon.v1.json"), (
        "the committed lexicon file must be loaded, not the embedded fallback "
        f"(got source={lex.source!r}, {len(lex.entries)} entries)"
    )
    assert len(lex.entries) > 80, f"expected the full 88-entry lexicon, got {len(lex.entries)}"
    assert any(e.canonical == "MTN Group Plc" for e in lex.entries)


def test_resolver_accepts_ner_predictions_and_keeps_them():
    ner = RuleBasedNer()
    resolver = StubPipeline().entity_resolver
    spans = ner.predict("Zenith Bank posted profits worth ₦459 billion, said the CBN.")
    resolved = resolver.resolve(spans)
    assert resolved, "resolver dropping every prediction is the silent-failure bug"
    names = {r.canonical_name for r in resolved}
    assert "Zenith Bank Plc" in names
    assert "Central Bank of Nigeria" in names


def test_entity_prediction_round_trip_preserves_spans():
    ner = RuleBasedNer()
    resolver = StubPipeline().entity_resolver
    spans = ner.predict("Access Holdings completed its recapitalisation.")
    resolved = resolver.resolve(spans)
    # Offsets unchanged: resolution annotates, it never re-tokenises.
    by_text = {}
    for pred in resolved:
        by_text.setdefault(pred.span.text, pred.span)
    for pred in spans:
        span = pred.span
        if span.entity_type.value == "EVENT_TRIGGER":
            continue
        assert span.text in by_text, f"mention {span.text!r} was dropped"
        kept = by_text[span.text]
        assert (kept.start, kept.end) == (span.start, span.end)


def test_mtn_collision_decision_table():
    pipeline = StubPipeline()

    def analyze(text: str):
        result = pipeline.analyze(text)
        return [(e.span.text, e.canonical_name, e.resolution_method) for e in result.entities]

    # Parent named explicitly -> parent, by surface form alone.
    r1 = analyze("MTN Group cut full-year guidance.")
    parent = [x for x in r1 if x[0] == "MTN Group"]
    assert parent and parent[0][1] == "MTN Group Plc", parent
    assert parent[0][2] in {"context", "alias"}, parent

    # Subsidiary named explicitly -> subsidiary.
    r2 = analyze("MTN Nigeria said subscriber growth accelerated.")
    sub = [x for x in r2 if x[0] == "MTN Nigeria"]
    assert sub and sub[0][1] == "MTN Nigeria Communications Plc", sub

    # Bare MTN with no hints -> honest "ambiguous", never a silent guess.
    r3 = analyze("MTN and rivals moved statements on tariffs.")
    bare = [x for x in r3 if x[0] == "MTN"]
    assert bare and bare[0][1] is None and bare[0][2] == "ambiguous", bare
