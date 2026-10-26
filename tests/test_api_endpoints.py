"""FastAPI endpoint tests against a throwaway SQLite database.

Mirrors scripts/smoke_api.py but as assertions. The app run here is the
production app with the deterministic stub pipeline — no trained weights
required.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Throwaway DB *before* the app (and its engine) is imported.
_TMP = tempfile.mkdtemp(prefix="naijafinsent-api-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"

API_DIR = Path(__file__).resolve().parents[1] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

SENTIMENT_LABELS = {"positive", "negative", "neutral", "uncertain"}


# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------

def test_root_serves_service_metadata():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body or "version" in body


def test_health_and_readiness():
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200


def test_openapi_is_served():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/v1/inference/analyze" in paths
    assert "/api/v1/events/" in paths  # collection routes carry a trailing slash


# ---------------------------------------------------------------------------
# Articles / events / entities (empty database, correct envelopes)
# ---------------------------------------------------------------------------

def test_articles_empty_envelope():
    resp = client.get("/api/v1/articles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["total"] == 0
    assert body["articles"] == []


def test_articles_404_for_unknown_id():
    assert client.get("/api/v1/articles/999999").status_code == 404


def test_events_and_clusters_envelopes():
    for url in ("/api/v1/events", "/api/v1/events/clusters"):
        resp = client.get(url)
        assert resp.status_code == 200, url
        body = resp.json()
        assert body["count"] == 0


def test_event_404_for_unknown_id():
    assert client.get("/api/v1/events/999999").status_code == 404


def test_entities_search_empty():
    resp = client.get("/api/v1/entities", params={"q": "zenith"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_entity_timeline_404_for_unknown_entity():
    resp = client.get("/api/v1/entities/999999/timeline")
    assert resp.status_code == 404
    # Even error paths must carry the disclaimer where the router defines one.


# ---------------------------------------------------------------------------
# Watchlists (write path)
# ---------------------------------------------------------------------------

def test_watchlist_create_list_duplicate_delete():
    created = client.post(
        "/api/v1/watchlists",
        json={"name": "banks", "entities": ["Zenith Bank"], "keywords": ["naira"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    watchlist_id = body["id"]
    assert watchlist_id is not None

    listed = client.get("/api/v1/watchlists")
    assert listed.status_code == 200
    assert any(w["id"] == watchlist_id for w in listed.json()["watchlists"])

    duplicate = client.post(
        "/api/v1/watchlists", json={"name": "banks", "entities": []}
    )
    assert duplicate.status_code == 409

    deleted = client.delete(f"/api/v1/watchlists/{watchlist_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.delete("/api/v1/watchlists/999999")
    assert missing.status_code == 404


def test_watchlist_requires_name():
    resp = client.post("/api/v1/watchlists", json={"entities": ["A"]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Inference: the deterministic demo path
# ---------------------------------------------------------------------------

def test_analyze_returns_labelled_sentiment_with_evidence():
    resp = client.post(
        "/api/v1/inference/analyze",
        json={"text": "The CBN raised the monetary policy rate amid rising inflation."},
    )
    assert resp.status_code == 200
    body = resp.json()
    label = body["sentiment"]["label"]
    assert label in SENTIMENT_LABELS
    assert 0.0 <= body["sentiment"]["confidence"] <= 1.0
    assert body["sentiment"]["evidence"], "evidence spans are mandatory"
    assert body["sentiment"]["model"]["name"]


def test_analyze_detects_events_with_evidence():
    resp = client.post(
        "/api/v1/inference/analyze",
        json={"text": "The Central Bank of Nigeria raised the monetary policy rate."},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert events
    assert events[0]["evidence"]


def test_analyze_flags_status_and_limitations():
    resp = client.post(
        "/api/v1/inference/analyze",
        json={"text": "Zenith Bank posted strong results."},
    )
    body = resp.json()
    assert body["status"] in {"ok", "complete", "partial"}
    # The not-investment-advice disclaimer travels with every result.
    joined = " ".join(body["limitations"]).lower()
    assert "not investment advice" in joined


def test_analyze_rejects_empty_text():
    resp = client.post("/api/v1/inference/analyze", json={"text": ""})
    assert resp.status_code in (400, 422)


def test_analyze_handles_the_naira_sign():
    resp = client.post(
        "/api/v1/inference/analyze",
        json={"text": "Access Bank posts ₦459 billion profit, up 34 percent."},
    )
    assert resp.status_code == 200
    # The corpus-facing language models must accept Nigerian financial text
    # end to end without unicode trouble.
    assert "sentiment" in resp.json()


# ---------------------------------------------------------------------------
# Models / notifications / news surface
# ---------------------------------------------------------------------------

def test_models_registry_envelope():
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    assert "models" in resp.json()


def test_notifications_envelope():
    resp = client.get("/api/v1/notifications")
    assert resp.status_code == 200
    assert "alerts" in resp.json()


def test_news_sources_is_listed():
    resp = client.get("/api/v1/news/sources")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert isinstance(sources, list)
