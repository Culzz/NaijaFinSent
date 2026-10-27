"""Nigerian-text handling — the roadmap's hard cases, enforced as tests.

Covers exactly what the credibility roadmap calls out:

* naira format variants   — ``₦1.2bn``, ``N1.2 billion``, ``1.2trn``, kobo,
  currency-after-word ("459 billion naira") — and the oil-bp trap
  (``1.2 million barrels`` must NOT be money);
* basis-point values       — ``50 basis points`` / ``300bps`` for the
  monetary-policy tracker;
* Pidgin sentences         — flow through the pipeline without crashing,
  always carring a valid 4-label sentiment and evidence;
* headline-style fragments — valid output, never a bare label;
* NGX ticker collisions    — ``Access Holdings`` vs ``Access Corp``, ``MTN
  Group`` vs ``MTN Nigeria`` resolve as separate entities with distinct
  canonical names;
* two-clock discipline     — event date vs publish date stay separate.

The sentiment *labels* on Pidgin are expected to be weak — that is exactly
what the gold-set gate measures (0.13–0.15). These tests demand *plumbing
integrity*, not lexical quality.
"""

from __future__ import annotations

from datetime import date

from naijafinsent.constants import SENTIMENT_LABELS
from naijafinsent.event_extraction.attributes import extract_values
from naijafinsent.inference.pipeline import StubPipeline
from naijafinsent.preprocessing.naira import find_money_mentions, parse_money

# --------------------------------------------------------------- money


def test_naira_format_variants_are_all_found():
    text = "Raised ₦1.2bn, N1.2 billion, 1.2trn and N25 kobo fees; 459 billion naira total."
    spans = {s.text for s in find_money_mentions(text)}
    assert "₦1.2bn" in spans
    assert "N1.2 billion" in spans
    assert "1.2trn" in spans                     # bare scaled amount kept
    assert "N25 kobo" in spans                   # never truncated to "N25 k"
    assert "459 billion naira" in spans          # currency-after form


def test_oil_barrels_are_not_money():
    spans = find_money_mentions("Production fell to 1.2 million barrels worth of output.")
    assert not any("1.2 million" == s.text for s in spans)


def test_parse_money_reads_every_variant():
    assert parse_money("₦1.2bn")["value"] == pytest_approx(1_200_000_000.0)
    assert parse_money("N1.2 billion")["currency"] == "NGN"
    assert parse_money("1.2trn")["unit"] == "trillion"
    assert parse_money("1.2trn")["currency"] is None      # never inferred
    assert parse_money("459 billion naira")["currency"] == "NGN"
    assert parse_money("N25 kobo")["currency"] == "NGN"


def pytest_approx(value: float) -> float:
    import pytest

    return pytest.approx(value)


def test_extract_values_covers_percent_bps_and_money():
    text = "Rate up 50 basis points to 27.5 percent; fine ₦50 million."
    values = extract_values(text)
    kinds = {v["kind"] for v in values}
    assert "percent" in kinds
    assert "basis_points" in kinds
    assert "money" in kinds
    bps = next(v for v in values if v["kind"] == "basis_points")
    assert bps["value"] == 50.0
    # Offsets must slice the original text exactly.
    for v in values:
        assert text[v["start"] : v["end"]] == v["text"], v


# ----------------------------------------------------------- pipeline


def _analyze(text: str):
    return StubPipeline().analyze(text)


def _sentiment_label(result) -> str:
    if isinstance(result, dict):
        label = (result.get("sentiment") or {}).get("label")
    else:
        label = getattr(getattr(result, "sentiment", None), "label", None)
    return getattr(label, "value", label)


def test_pidgin_sentences_flow_through_with_valid_shape():
    for text in (
        "Bank don declare dividend, shareholders dey happy well well.",
        "Naira don fall again for parallel market, dollar cost ₦1,700 today.",
        "Market no dey move today, everybody just dey look.",
    ):
        result = _analyze(text)
        assert _sentiment_label(result) in SENTIMENT_LABELS
        sent = result["sentiment"] if isinstance(result, dict) else result.sentiment
        evidence = sent["evidence"] if isinstance(result, dict) else sent.evidence
        assert evidence, "pidgin text still needs evidence spans"


def test_pidgin_naira_mention_is_extracted_as_entity():
    result = _analyze("Naira don fall again for parallel market, dollar cost ₦1,700 today.")
    entities = result["entities"] if isinstance(result, dict) else result.entities
    money_texts = [_canonical(e) for e in entities]
    assert any("₦1,700" in t for t in money_texts if t), money_texts


def test_headline_fragments_produce_labelled_evidence():
    for text in ("NPAT +34% y/y; final div ₦3.10; qual date Mar 5.", "CBN keeps rate at 27.50%; CRR 45%."):
        result = _analyze(text)
        assert _sentiment_label(result) in SENTIMENT_LABELS
        assert (_result_evidence(result))


def _result_evidence(result) -> list:
    sent = result["sentiment"] if isinstance(result, dict) else result.sentiment
    return sent["evidence"] if isinstance(result, dict) else sent.evidence


def test_ticker_collision_entities_resolve_as_distinct_names():
    from naijafinsent.entity_resolution import resolver as _res  # noqa: F401  (import guard)

    result = _analyze("MTN Group cut guidance, though MTN Nigeria kept its outlook unchanged.")
    entities = result["entities"] if isinstance(result, dict) else result.entities
    names = {_canonical(e) for e in entities}
    assert any("MTN Group" in n for n in names), f"expected MTN Group in {names}"
    assert any("MTN Nigeria" in n for n in names), "parent and subsidiary must not merge"


def _canonical(entity) -> str:
    if isinstance(entity, dict):
        return (
            entity.get("canonical_name")
            or entity.get("text")
            or (entity.get("span") or {}).get("text")
            or ""
        )
    span = getattr(entity, "span", None)
    return (
        getattr(entity, "canonical_name", None)
        or getattr(entity, "text", None)
        or getattr(span, "text", "")
        or ""
    )


def test_mpc_bps_value_travels_through_events():
    result = _analyze("The MPC raised the monetary policy rate by 50 basis points to 27.75 percent.")
    events = result["events"] if isinstance(result, dict) else result.events
    policy_events = [e for e in events if _etype(e) == "cbn_policy"]
    assert policy_events, "the policy event must be detected"
    attrs = policy_events[0]["attributes"] if isinstance(policy_events[0], dict) else policy_events[0].attributes
    texts = [v["text"] for v in (attrs.get("values") or [])]
    assert any("basis points" in t for t in texts), f"expected bps in {texts}"
    assert any("27.75" in t for t in texts), f"expected the percent level in {texts}"


def _etype(event) -> str:
    if isinstance(event, dict):
        value = event.get("event_type")
    else:
        value = getattr(event, "event_type", None)
    return getattr(value, "value", value)


def test_publish_date_is_never_used_as_the_event_date():
    from naijafinsent.event_extraction.attributes import extract_event_date

    event_date, basis = extract_event_date(
        "The board met on 12 March 2026 and approved the payout.",
        publish_date=date(2026, 10, 20),
    )
    assert event_date == date(2026, 3, 12)
    assert basis == "absolute"
