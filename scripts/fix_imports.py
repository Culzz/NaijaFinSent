"""Rewrite `services.api.app` imports to `app` so the API is importable with
PYTHONPATH=services/api. Run once."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "api" / "app"

changed = 0
for path in API.rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    if "services.api.app" in text:
        new = text.replace("services.api.app", "app").replace(
            "from app.app", "from app"
        )
        path.write_text(new, encoding="utf-8")
        changed += 1
        print("rewrote", path.relative_to(ROOT))
print("files changed:", changed)
