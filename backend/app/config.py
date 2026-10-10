"""Runtime configuration, read from environment variables (or backend/.env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEV_API_KEY = "dev-local-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_prefix="AOBS_", extra="ignore")

    environment: str = "development"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'observability.db').as_posix()}"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    # Comma-separated. Ingest clients and the dashboard send one in X-API-Key.
    api_keys: str = DEV_API_KEY
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Retrain the classifier automatically after this many new human labels (0 disables).
    auto_retrain_every: int = 50

    @property
    def api_key_list(self) -> List[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
