"""Every shipped manifest entry must validate against the shared schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from naijafinsent.constants import TRUST_TIERS
from naijafinsent.data.sources import (
    ManifestError,
    get_source,
    load_manifest_file,
    load_manifests,
)
from naijafinsent.schemas import SourceManifestEntry

MANIFEST = (
    Path(__file__).resolve().parent.parent / "data" / "manifests" / "sources.json"
)

EXPECTED_SOURCE_IDS = {
    "businessday",
    "nairametrics",
    "punch",
    "premium_times",
    "cbn",
    "ngx",
    "sec_ng",
}


def test_manifest_file_exists():
    assert MANIFEST.exists(), f"missing manifest: {MANIFEST}"


def test_manifest_has_wrapper_fields():
    doc = load_manifest_file(MANIFEST)
    assert doc["version"] == "1.0"
    assert "generated_at" in doc
    assert isinstance(doc["sources"], list)


def test_every_entry_validates_against_schema():
    manifests = load_manifests(MANIFEST)
    assert manifests, "manifest produced no entries"
    for entry in manifests:
        # Round-trip through the strict model (extra=forbid).
        assert isinstance(entry, SourceManifestEntry)
        SourceManifestEntry.model_validate(entry.model_dump())


def test_all_seven_sources_present():
    manifests = load_manifests(MANIFEST)
    assert {m.source_id for m in manifests} == EXPECTED_SOURCE_IDS


def test_trust_tiers_are_valid():
    for entry in load_manifests(MANIFEST):
        assert entry.trust_tier in TRUST_TIERS


def test_access_methods_are_valid():
    valid = {"rss", "sitemap", "html", "api"}
    for entry in load_manifests(MANIFEST):
        assert entry.access_method in valid


def test_official_sources_are_official_tier():
    official_ids = {"cbn", "ngx", "sec_ng"}
    for entry in load_manifests(MANIFEST):
        if entry.source_id in official_ids:
            assert entry.trust_tier == "official"
        else:
            assert entry.trust_tier == "tier1"


def test_url_patterns_compile_as_regex():
    import re

    for entry in load_manifests(MANIFEST):
        re.compile(entry.url_pattern)  # raises if invalid


def test_license_notes_reflect_conservative_policy():
    # Every manifest entry must state that redistribution is not cleared yet.
    for entry in load_manifests(MANIFEST):
        note = entry.license_note.lower()
        assert "unverified" in note
        assert "url" in note and "labels" in note


def test_entries_are_extra_forbid():
    # An unknown key must be rejected (guards against silent schema drift).
    bad = {
        "source_id": "x",
        "name": "X",
        "base_url": "https://x.example",
        "url_pattern": ".*",
        "access_method": "html",
        "license_note": "unverified",
        "trust_tier": "tier1",
        "unknown_field": True,
    }
    with pytest.raises(Exception):
        SourceManifestEntry.model_validate(bad)


def test_get_source_roundtrip():
    entry = get_source("businessday", MANIFEST)
    assert entry.name == "BusinessDay"
    with pytest.raises(KeyError):
        get_source("does_not_exist", MANIFEST)


def test_load_manifests_missing_file_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_manifests(tmp_path / "nope.json")


def test_load_manifests_bare_list_form(tmp_path):
    # A bare list (no wrapper) is also accepted for flexibility.
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_id": "example",
                    "name": "Example",
                    "base_url": "https://example.com",
                    "url_pattern": r"https://example\.com/",
                    "access_method": "rss",
                    "license_note": "unverified; link only. We publish article url and labels.",
                    "trust_tier": "tier2",
                }
            ]
        ),
        encoding="utf-8",
    )
    manifests = load_manifests(path)
    assert len(manifests) == 1
    assert manifests[0].source_id == "example"
