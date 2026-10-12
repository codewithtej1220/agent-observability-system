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
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Retrain the classifier automatically after this many new human labels (0 disables).
    auto_retrain_every: int = 50

    # --- Security -------------------------------------------------------
    # Fernet key(s) used to encrypt stored provider API keys. Comma-separate
    # to rotate (first one encrypts). Required in production.
    secret_key: str = ""
    # Development-only API key mapped to the demo workspace (ignored in production).
    dev_api_key: str = DEV_API_KEY
    session_days: int = 14
    # Set to true when served over HTTPS so the session cookie is Secure.
    cookie_secure: bool = False

    # --- Google sign-in (optional) ---------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    # Public URL of the dashboard; Google redirects to {public_url}/api/auth/google/callback.
    public_url: str = "http://localhost:5173"

    # --- LLM gateway -----------------------------------------------------
    # URL your applications use to reach this API (shown in setup instructions).
    api_public_url: str = "http://127.0.0.1:8000"
    openai_base_url: str = "https://api.openai.com"
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gateway_timeout_s: float = 120.0

    # --- Background jobs (evaluation queue, alerts, drift tests, retention)
    background_jobs: bool = True

    # --- Email alerts (optional) -----------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def dev_key_enabled(self) -> bool:
        return self.environment != "production" and bool(self.dev_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
