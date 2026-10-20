"""Central configuration. Read once, from env vars / .env, never from W&B."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "development"
    log_level: str = "INFO"

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 60
    max_text_chars: int = 20_000
    max_batch_size: int = 32

    # Ingestion
    user_agent: str = (
        "NaijaFinSent-ResearchBot/0.1 (+https://github.com/Culzz/NaijaFinSent)"
    )
    fetch_rate_limit_seconds: float = 2.0
    fetch_max_bytes: int = 2_000_000
    fetch_timeout_seconds: float = 20.0
    fetch_max_redirects: int = 5
    ingest_cron: str = "0 */6 * * *"

    # Storage
    database_url: str = "sqlite:///./data/naijafinsent.db"
    data_dir: Path = REPO_ROOT / "data"
    models_dir: Path = REPO_ROOT / "data" / "models"
    model_registry_path: Path = REPO_ROOT / "data" / "models" / "registry.json"

    # Optional
    anthropic_api_key: str | None = None
    wandb_project: str | None = None

    # Non-goal reminders surfaced in the UI / API docs.
    disclaimer: str = (
        "NaijaFinSent measures language in published news coverage. "
        "It is not investment advice and makes no causal or predictive claims "
        "about prices or returns."
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.models_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
