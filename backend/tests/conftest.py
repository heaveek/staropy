"""Shared pytest fixtures: SQLite-backed app, seeded content, signed initData.

No real Telegram token is required — tests use a deterministic fake bot token
and build correctly-signed initData strings via the same HMAC algorithm.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import pytest

# --- environment must be set before importing the app ------------------------
TEST_DB = f"sqlite:///{uuid.uuid4().hex}.test.db"
os.environ["DATABASE_URL_OVERRIDE"] = TEST_DB
os.environ["ALLOW_DEV_AUTH"] = "true"
os.environ["APP_ENV"] = "development"
os.environ["PAYMENTS_ENABLED"] = "false"
os.environ["PAYMENT_PROVIDER"] = "stub"
os.environ["FREE_READINGS_PER_DAY"] = "1"
os.environ["FREE_HISTORY_LIMIT"] = "3"
os.environ["INTERNAL_API_SECRET"] = "test_internal_secret_not_a_real_token"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BOT_TOKEN = "test:FAKE_BOT_TOKEN_for_unit_tests_only"
os.environ["TELEGRAM_BOT_TOKEN"] = BOT_TOKEN

from app.config import get_settings  # noqa: E402
from app.core.security import build_init_data_for_tests  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_session_factory, reset_engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _app_db():
    reset_engine()
    engine = get_engine()
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    path = TEST_DB.replace("sqlite:///", "")
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import create_app

    # Defense-in-depth: if an earlier test leaked a settings mutation through
    # the module-level @lru_cache on get_settings(), rebind the cache to the
    # pristine environment values so every API test starts from a known state.
    get_settings.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as c:
            yield c
    finally:
        get_settings.cache_clear()


@pytest.fixture()
def seed():
    """Load tarot content into the test DB once per test (idempotent)."""
    from app.seed.load_content import load_content

    session = get_session_factory()()
    try:
        load_content(session)
    finally:
        session.close()


def make_init_data(tg_user: dict, token: str = BOT_TOKEN, auth_ts: int | None = None) -> str:
    payload = {
        "auth_date": str(auth_ts if auth_ts is not None else int(time.time())),
        "query_id": uuid.uuid4().hex[:18],
        "user": json.dumps(tg_user),
        "version": "7.0",
    }
    return build_init_data_for_tests(payload, token)


def user_headers(tg_id: int = 111, **extra) -> dict:
    tg_user = {"id": tg_id, "first_name": "Test", "username": f"user_{tg_id}"}
    init_data = make_init_data({**tg_user, **extra})
    return {"X-Telegram-Init-Data": init_data}


@pytest.fixture()
def fresh_tg_id():
    """Unique telegram id per test to avoid quota cross-contamination."""
    return 900_000_000 + uuid.uuid4().int % 100_000_000


INTERNAL_SECRET = os.environ["INTERNAL_API_SECRET"]


def sign_internal(body: bytes, secret: str = INTERNAL_SECRET) -> str:
    """HMAC-SHA256 over the exact request body (matches bot/backend_client)."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def internal_headers(body: bytes, secret: str = INTERNAL_SECRET) -> dict:
    return {"Content-Type": "application/json",
            "X-Internal-Signature": sign_internal(body, secret)}
