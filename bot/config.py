"""Bot configuration from environment variables. No secrets in source."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BotSettings:
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webapp_url: str = ""
    backend_base_url: str = "http://backend:8000"
    internal_api_secret: str = ""
    log_level: str = "INFO"

    @staticmethod
    def from_env(environ: dict | None = None) -> "BotSettings":
        env = environ if environ is not None else dict(os.environ)
        return BotSettings(
            telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_bot_username=env.get("TELEGRAM_BOT_USERNAME", "").strip(),
            telegram_webapp_url=env.get("TELEGRAM_WEBAPP_URL", "").strip(),
            backend_base_url=env.get("BACKEND_BASE_URL", "http://backend:8000").rstrip("/"),
            internal_api_secret=env.get("INTERNAL_API_SECRET", "").strip(),
            log_level=env.get("LOG_LEVEL", "INFO"),
        )

    @property
    def mini_app_button_url(self) -> str:
        """tg://app deep link opens the Mini App inside Telegram chat."""
        if self.telegram_bot_username and self.telegram_webapp_url:
            from urllib.parse import quote
            return f"tg://app?bot_username={self.telegram_bot_username}&appid=&url={quote(self.telegram_webapp_url, safe='')}"
        return self.telegram_webapp_url or ""


@dataclass
class RuntimeFlags:
    """Mutable runtime knobs kept out of frozen settings."""
    payments_enabled: bool = field(
        default_factory=lambda: _truthy(os.environ.get("PAYMENTS_ENABLED", "false"))
    )


def require_token(settings: BotSettings) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not configured. The bot cannot start without a token. "
            "Set it via environment variable (see .env.example)."
        )
