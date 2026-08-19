"""
Application configuration.

All runtime configuration is loaded from environment variables (via a
`.env` file in local/dev, or real environment variables in
staging/production) using pydantic-settings. Nothing here should be
hard-coded — this is the single source of truth for config across the app.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App -----------------------------------------------------------
    app_name: str = "FieldCheck AI"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    cors_origins: str = "http://localhost:3000"

    # --- Security --------------------------------------------------------
    secret_key: str = "insecure-dev-secret-change-me"
    internal_api_key: str = ""
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # --- Database --------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./fieldcheck.db"

    # --- Storage ---------------------------------------------------------
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 15
    allowed_mime_types: str = "image/jpeg,image/png"

    # --- Async processing --------------------------------------------------
    use_celery: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- Vision AI ---------------------------------------------------------
    vision_provider: str = "openai"  # "openai" | "anthropic"

    openai_api_key: str = ""
    openai_vision_model: str = "gpt-4o"

    anthropic_api_key: str = ""
    anthropic_vision_model: str = "claude-3-5-sonnet-20241022"

    vision_timeout_seconds: int = 45
    vision_max_retries: int = 3
    vision_mock_mode: bool = True

    # --- Reporting -----------------------------------------------------------
    report_output_dir: str = "./output_reports"
    company_name: str = "FieldCheck AI Demo Co."

    # --- Email (inspection report delivery) -------------------------------
    # Mirrors the vision_mock_mode pattern: when true (default), no real SMTP
    # connection is made — the email is "sent" to a local mock outbox
    # (report_output_dir/mock_outbox/) so the whole flow is demoable offline.
    email_mock_mode: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_address: str = "no-reply@fieldcheck.ai"
    smtp_from_name: str = "FieldCheck AI"

    @property
    def email_smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_address)

    @field_validator("app_env")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.lower().strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_mime_type_list(self) -> list[str]:
        return [m.strip() for m in self.allowed_mime_types.split(",") if m.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def report_output_path(self) -> Path:
        p = Path(self.report_output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vision_api_key_configured(self) -> bool:
        if self.vision_provider == "openai":
            return bool(self.openai_api_key)
        if self.vision_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — env is read once per process."""
    return Settings()


settings = get_settings()
