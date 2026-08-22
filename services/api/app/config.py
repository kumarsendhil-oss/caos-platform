"""
Centralized configuration, per Coding Guidelines CG4.

Every setting the platform needs — database, Redis, Tally, Zoho OAuth, GSP,
OCR — goes through this single Settings object. Nothing outside this file
should call os.environ[...] or os.environ.get(...) directly.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "dev-only-change-me"  # noqa: S105 — overridden via .env / Secrets Manager in real envs

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./caos_dev.db"

    # --- Redis / Celery (ADR 0007, ADR 0003) ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Books Connector — Tally adapter (ADR 0001) ---
    tally_connector_host: str = ""
    tally_connector_port: int = 9000

    # --- Books Connector — Zoho adapter (ADR 0011) ---
    zoho_oauth_client_id: str = ""
    zoho_oauth_client_secret: str = ""
    zoho_oauth_redirect_uri: str = "http://localhost:8000/auth/zoho/callback"

    # --- GSP (ADR 0002) ---
    gsp_provider: str = "whitebooks"
    gsp_client_id: str = ""
    gsp_client_secret: str = ""
    gsp_base_url: str = "https://apisandbox.whitebooks.in/gst"

    # --- Auth (Security Standard §1) ---
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 8

    # --- Practice identity (ADR 0010 — base-product model) ---
    practice_id: str = "venture-assist-srivatsan"
    practice_slug: str = "venture_assist_srivatsan"


settings = Settings()  # type: ignore[call-arg]
