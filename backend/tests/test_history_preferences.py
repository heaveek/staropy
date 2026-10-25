"""History windowing + preferences endpoints tests (spec §2.3, §11)."""
from __future__ import annotations

import uuid

from tests.conftest import user_headers


def _make_reading(client, headers, theme="love"):
    body = {"spread_code": "daily_card", "theme_code": theme, "question": None,
            "idempotencyKey": uuid.uuid4().hex}
    return client.post("/api/v1/readings", json=body, headers=headers)


def _grant_premium(tg_id: int):
    from app.db.session import get_session_factory
    from app.models import User
    from app.services.domain import grant_premium

    session = get_session_factory()()
    uid = session.query(User).filter_by(telegram_id=tg_id).one().id
    grant_premium(session, uid, duration_days=30, source="admin", external_payment_id=None)
    session.commit()
    session.close()


def test_history_empty_state(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    r = client.get("/api/v1/readings", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


def test_history_shows_created_readings(client, seed, fresh_tg_id):
    _grant_premium_needed = False
    headers = user_headers(fresh_tg_id)
    # premium so quota doesn't block multiple readings
    client.get("/api/v1/auth/me", headers=headers)
    _grant_premium(fresh_tg_id)
    for theme in ("love", "work", "money"):
        assert _make_reading(client, headers, theme=theme).status_code == 200

    r = client.get("/api/v1/readings?limit=50", headers=headers)
    data = r.json()
    assert len(data["items"]) == 3
    assert data["limited_by_plan"] is False
    item = data["items"][0]
    assert item["card_names"], "summary must include card names"
    assert item["spread_name"]


def test_free_history_limited_to_three(client, seed, fresh_tg_id):
    """Free plan: backend caps visible history to FREE_HISTORY_LIMIT."""
    headers = user_headers(fresh_tg_id)
    client.get("/api/v1/auth/me", headers=headers)  # create user
    _grant_premium(fresh_tg_id)
    for i in range(5):  # create 5 readings while premium
        assert _make_reading(client, headers, theme=["love", "work", "money", "self_development", "health"][i]).status_code == 200

    # revoke premium by expiring entitlements
    from app.db.session import get_session_factory
    from app.models import Entitlement
    session = get_session_factory()()
    from app.models import User
    uid = session.query(User).filter_by(telegram_id=fresh_tg_id).one().id
    for e in session.query(Entitlement).filter_by(user_id=uid):
        e.status = "expired"
    session.commit()
    session.close()

    r = client.get("/api/v1/readings?limit=50", headers=headers)
    data = r.json()
    assert len(data["items"]) <= 3
    assert data["limited_by_plan"] is True


def test_history_pagination_cursor(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    client.get("/api/v1/auth/me", headers=headers)
    _grant_premium(fresh_tg_id)
    ids = set()
    for i in range(4):
        resp = _make_reading(client, headers, theme=["love", "work", "money", "health"][i])
        ids.add(resp.json()["reading_id"])

    page1 = client.get("/api/v1/readings?limit=2", headers=headers).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"]
    page2 = client.get(f"/api/v1/readings?limit=2&cursor={page1['next_cursor']}", headers=headers).json()
    assert len(page2["items"]) == 2
    seen = {i["reading_id"] for i in page1["items"]} | {i["reading_id"] for i in page2["items"]}
    assert seen == ids


def test_bad_cursor_rejected(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    r = client.get("/api/v1/readings?cursor=notbase64!!!", headers=headers)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


# ---------------------------------------------------------------- preferences

def test_preferences_roundtrip(client, seed, fresh_tg_id):
    headers = user_headers(fresh_tg_id)
    r = client.get("/api/v1/users/me/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["daily_reminder_enabled"] is False

    p = client.patch("/api/v1/users/me/preferences",
                     json={"daily_reminder_enabled": True, "timezone": "Europe/Berlin"},
                     headers=headers)
    assert p.status_code == 200
    assert p.json()["daily_reminder_enabled"] is True
    assert p.json()["timezone"] == "Europe/Berlin"

    again = client.get("/api/v1/users/me/preferences", headers=headers).json()
    assert again["daily_reminder_enabled"] is True
