"""API smoke test with the FastAPI TestClient (run directly, not pytest)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Use a throwaway SQLite file before importing the app.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"

import sys  # noqa: E402

sys.path.insert(0, "services/api")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

checks: list[tuple[str, str, int]] = []

for method, url in [
    ("GET", "/"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),
    ("GET", "/api/v1/articles"),
    ("GET", "/api/v1/events"),
    ("GET", "/api/v1/events/clusters"),
    ("GET", "/api/v1/models"),
    ("GET", "/api/v1/watchlists"),
    ("GET", "/api/v1/notifications"),
    ("POST", "/api/v1/watchlists"),
    ("GET", "/api/v1/news/sources"),
    ("GET", "/openapi.json"),
]:
    kwargs = {"json": {"name": "banks", "entities": ["Zenith Bank"]}} if method == "POST" else {}
    resp = getattr(client, method.lower())(url, **kwargs)
    checks.append((method, url, resp.status_code))
    print(f"{method} {url} -> {resp.status_code}")

bad = [c for c in checks if c[2] >= 500]
if bad:
    raise SystemExit(f"5xx failures: {bad}")

# Inference endpoint (deterministic stub path).
resp = client.post("/api/v1/inference/analyze", json={"text": "The CBN raised the MPR."})
print("POST /analyze ->", resp.status_code, list(resp.json())[:5])

print("API SMOKE OK")
