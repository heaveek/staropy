"""Unit tests for Telegram initData HMAC verification (spec §13)."""
from __future__ import annotations

import json
import time

import pytest

from app.core.security import build_init_data_for_tests, verify_init_data
from tests.conftest import BOT_TOKEN, make_init_data


def test_valid_init_data_roundtrip():
    init_data = make_init_data({"id": 42, "first_name": "Ada"})
    fields = verify_init_data(init_data, BOT_TOKEN)
    user = json.loads(fields["user"])
    assert user["id"] == 42


def test_missing_hash_rejected():
    payload = {"auth_date": str(int(time.time())), "user": "{}"}
    raw = "&".join(f"{k}={v}" for k, v in payload.items())
    with pytest.raises(ValueError) as exc:
        verify_init_data(raw, BOT_TOKEN)
    assert str(exc.value) == "missing_hash"


def test_tampered_payload_rejected():
    init_data = make_init_data({"id": 42})
    # flip one char of the signed user field
    tampered = init_data.replace("user_42", "user_43") if "user_42" in init_data else init_data + "&x=1"
    with pytest.raises(ValueError):
        verify_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    init_data = make_init_data({"id": 7}, token="test:OTHER_TOKEN")
    with pytest.raises(ValueError) as exc:
        verify_init_data(init_data, BOT_TOKEN)
    assert str(exc.value) == "invalid_signature"


def test_expired_auth_date_rejected():
    old = int(time.time()) - 3 * 86400
    init_data = make_init_data({"id": 9}, auth_ts=old)
    with pytest.raises(ValueError) as exc:
        verify_init_data(init_data, BOT_TOKEN, max_age_seconds=86400)
    assert str(exc.value) == "auth_date_expired"


def test_empty_init_data_rejected():
    with pytest.raises(ValueError):
        verify_init_data("", BOT_TOKEN)


def test_no_token_configured():
    init_data = make_init_data({"id": 1})
    with pytest.raises(ValueError) as exc:
        verify_init_data(init_data, "")
    assert str(exc.value) == "bot_token_not_configured"


def test_builder_output_is_url_safe_and_verifiable():
    payload = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 5, "first_name": "Иван"})}
    s = build_init_data_for_tests(payload, BOT_TOKEN)
    fields = verify_init_data(s, BOT_TOKEN)
    assert json.loads(fields["user"])["first_name"] == "Иван"
