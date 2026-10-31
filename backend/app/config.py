"""Application configuration loaded from environment variables (.env aware)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "development"  # development | production | test
    app_name: str = "Tarot Mini App"
    app_timezone: str = "Europe/Moscow"
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+psycopg://tarot:change_me@localhost:5432/tarot"

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webapp_url: str = ""
    telegram_initdata_max_age_seconds: int = 86400
    admin_telegram_ids: str = ""

    # Limits
    free_readings_per_day: int = 1
    free_history_limit: int = 3
    question_max_length: int = 500

    # Payments
    payments_enabled: bool = False
    payment_provider: str = "telegram_stars"

    # Shared secret for the internal API (bot -> backend payment events).
    # Empty means the internal endpoints are disabled (fail closed).
    internal_api_secret: str = ""

    # Development-only auth escape hatch. Never allowed in production.
    allow_dev_auth: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def dev_auth_allowed(self) -> bool:
        return self.allow_dev_auth and not self.is_production

    @property
    def admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if part:
                try:
                    ids.add(int(part))
                except ValueError:
                    continue
        return ids

    def validate_production(self) -> list[str]:
        """Return a list of configuration problems for production runs."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if not self.telegram_bot_token:
            problems.append("TELEGRAM_BOT_TOKEN is required in production")
        if self.allow_dev_auth:
            problems.append("ALLOW_DEV_AUTH must not be enabled in production")
        if self.database_url.startswith("sqlite"):
            problems.append("PostgreSQL is required in production")
        if self.app_base_url.startswith("http://"):
            problems.append("APP_BASE_URL must use HTTPS in production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
