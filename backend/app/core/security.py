"""Telegram Web App initData verification (HMAC-SHA-256) per official algorithm."""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl

from ..config import get_settings


def _secret_key(bot_token: str) -> bytes:
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return secret


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int | None = None) -> dict:
    """Validate Telegram WebApp initData string.

    Returns the parsed payload dict on success.
    Raises ValueError with a stable reason on failure.
    """
    if not init_data or not bot_token:
        raise ValueError("missing_init_data" if not init_data else "bot_token_not_configured")

    settings = get_settings()
    if max_age_seconds is None:
        max_age_seconds = settings.telegram_initdata_max_age_seconds

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True)
    except Exception:  # pragma: no cover - defensive
        raise ValueError("malformed_init_data")

    fields: dict[str, str] = {}
    hash_value: str | None = None
    for key, value in pairs:
        if key == "hash":
            hash_value = value
        else:
            fields[key] = value

    if hash_value is None:
        raise ValueError("missing_hash")
    if "auth_date" not in fields:
        raise ValueError("missing_auth_date")

    # Check age
    try:
        auth_date = int(fields["auth_date"])
    except ValueError:
        raise ValueError("invalid_auth_date")
    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise ValueError("auth_date_expired")

    # Data check string: sorted key=value lines, excluding hash
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = _secret_key(bot_token)
    computed = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, hash_value):
        raise ValueError("invalid_signature")

    return fields


def build_init_data_for_tests(payload: dict[str, str], bot_token: str) -> str:
    """Create a correctly signed initData string. Intended for local dev/tests only."""
    from urllib.parse import quote

    items = dict(payload)
    data_check_string = "\n".join(f"{k}={items[k]}" for k in sorted(items))
    secret_key = _secret_key(bot_token)
    hash_value = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    parts = [f"{k}={quote(v, safe='')}" for k, v in items.items()]
    parts.append(f"hash={hash_value}")
    return "&".join(parts)
