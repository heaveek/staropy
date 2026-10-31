"""API tests: auth flow, catalog, reading creation, quota and premium rules."""
from __future__ import annotations

import uuid

from tests.conftest import user_headers


def _create_reading(client, headers, spread="daily_card", theme="love", question=None):
    body = {
        "spread_code": spread,
        "theme_code": theme,
        "question": question,
        "idempotencyKey": uuid.uuid4().hex,
    }
    return client.post("/api/v1/readings", json=body, headers=headers)


# ---------------------------------------------------------------- auth

def test_me_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_with_signed_init_data(client, seed, fresh_tg_id):
    r = client.get("/api/v1/auth/me", headers=user_headers(fresh_tg_id))
    assert r.status_code == 200
    data = r.json()
    assert data["telegram_id"] == fresh_tg_id
    assert data["premium"]["is_premium"] is False
    assert data["quota"]["free_readings_remaining"] == 1
    assert data["history_limit"] == 3


def test_auth_telegram_endpoint(client, seed, fresh_tg_id):
    from tests.conftest import make_init_data
    init_data = make_init_data({"id": fresh_tg_id, "first_name": "Ann"})
    r = client.post("/api/v1/auth/telegram", json={"initData": init_data})
    assert r.status_code == 200
    assert r.json()["user"]["telegram_id"] == fresh_tg_id


def test_auth_telegram_rejects_bad_signature(client):
    r = client.post("/api/v1/auth/telegram", json={"initData": "user=x&auth_date=1&hash=deadbeef"})
    assert r.status_code == 401
    assert r.json()["error"]["details"]["reason"] in ("invalid_signature", "auth_date_expired")


def test_blocked_user_forbidden(client, seed, fresh_tg_id):
    from app.db.session import get_session_factory
    from app.models import User

    session = get_session_factory()()
    client.get("/api/v1/auth/me", headers=user_headers(fresh_tg_id))  # create user
    u = session.query(User).filter_by(telegram_id=fresh_tg_id).one()
    u.is_blocked = True
    session.commit()
    session.close()
    r = client.get("/api/v1/auth/me", headers=user_headers(fresh_tg_id))
    assert r.status_code == 403


# ---------------------------------------------------------------- catalog

def test_catalog_lists_themes_and_spreads(client, seed):
    r = client.get("/api/v1/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["themes"]) >= 4
    codes = {s["code"] for s in data["spreads"]}
    assert {"daily_card", "yes_no", "past_present_future",
            "situation_advice_outcome", "celtic_cross"} <= codes
    celtic = next(s for s in data["spreads"] if s["code"] == "celtic_cross")
    assert celtic["is_premium"] is True
    assert len(celtic["positions"]) == 10


# ---------------------------------------------------------------- readings & quota

def test_create_daily_reading_free(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    r = _create_reading(client, headers)
    assert r.status_code == 200, r.text
    rid = r.json()["reading_id"]

    detail = client.get(f"/api/v1/readings/{rid}", headers=headers)
    assert detail.status_code == 200
    d = detail.json()
    assert d["spread_code"] == "daily_card"
    assert len(d["cards"]) == 1
    assert d["disclaimer"], "disclaimer must be present"
    assert d["snapshot"]["positions"][0]["card_name_ru"]


def test_quota_consumed_and_second_reading_blocked(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    ok = _create_reading(client, headers)
    assert ok.status_code == 200
    second = _create_reading(client, headers, theme="work")
    assert second.status_code == 402
    assert second.json()["error"]["code"] == "limit_reached"

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["quota"]["free_readings_remaining"] == 0


def test_idempotent_replay_does_not_consume_quota(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    key = uuid.uuid4().hex
    body = {"spread_code": "past_present_future", "theme_code": "money", "question": None,
            "idempotencyKey": key}
    r1 = client.post("/api/v1/readings", json=body, headers=headers)
    r2 = client.post("/api/v1/readings", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["reading_id"] == r2.json()["reading_id"]
    assert r2.json()["replayed"] is True
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["quota"]["free_readings_used_today"] == 1


def test_celtic_cross_requires_premium(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    r = _create_reading(client, headers, spread="celtic_cross")
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "premium_required"


def test_premium_user_can_use_celtic_cross(client, seed, fresh_tg_id):
    from app.db.session import get_session_factory
    from app.services.domain import grant_premium

    session = get_session_factory()()
    client.get("/api/v1/auth/me", headers=user_headers(fresh_tg_id))
    from app.models import User
    uid = session.query(User).filter_by(telegram_id=fresh_tg_id).one().id
    grant_premium(session, uid, duration_days=30, source="admin", external_payment_id=None)
    session.commit()
    session.close()

    headers = user_headers(fresh_tg_id)
    r = _create_reading(client, headers, spread="celtic_cross", theme="self_development")
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/v1/readings/{r.json()['reading_id']}", headers=headers).json()
    assert len(detail["cards"]) == 10
    assert detail["is_free"] is False


def test_unknown_spread_or_theme(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    assert _create_reading(client, headers, spread="nope").json()["error"]["code"] == "spread_not_found"
    assert _create_reading(client, headers, theme="nope").json()["error"]["code"] == "theme_not_found"


def test_question_length_validation(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    long_q = "вопрос?" * 100  # 700 chars > QUESTION_MAX_LENGTH=500
    r = _create_reading(client, headers, question=long_q)
    assert r.status_code in (400, 422)


def test_reading_not_visible_to_other_users(client, seed, fresh_tg_id):
    h1 = user_headers(fresh_tg_id)
    rid = _create_reading(client, h1).json()["reading_id"]
    h2 = user_headers(fresh_tg_id + 1)
    r = client.get(f"/api/v1/readings/{rid}", headers=h2)
    assert r.status_code == 404
