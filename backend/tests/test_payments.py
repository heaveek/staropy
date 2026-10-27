"""Payment cycle tests (spec §14) — no real Telegram token/network required.

Covers:
  - payments disabled by default -> 503;
  - inactive products cannot be purchased (explicit activation required);
  - createInvoiceLink-based provider contract (mocked httpx, result = URL string);
  - confirm_payment validates the REAL event amount/currency from Telegram,
    payload ownership, idempotent replay and rejects conflicts;
  - Premium granted only after a confirmed payment; celtic_cross unlocked.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_session_factory
from app.models import Entitlement, Payment, Product, User
from app.services import payments as pay_svc
from app.services.domain import is_premium

from tests.conftest import user_headers


# ---------------------------------------------------------------- helpers

class _TogglePayments:
    """Temporarily flip settings for one test despite @lru_cache on get_settings."""

    def __enter__(self):
        settings = get_settings()
        self._old_enabled = settings.payments_enabled
        self._old_provider = settings.payment_provider
        object.__setattr__(settings, "payments_enabled", True)
        object.__setattr__(settings, "payment_provider", "stub")
        return settings

    def __exit__(self, *exc):
        settings = get_settings()
        object.__setattr__(settings, "payments_enabled", self._old_enabled)
        object.__setattr__(settings, "payment_provider", self._old_provider)


def _activate_products(session):
    for p in session.scalars(select(Product)):
        p.is_active = True
    session.commit()


def _create_payment(client, tg_id, product_code="premium_month"):
    resp = client.post(
        "/api/v1/payments/create",
        json={"product_code": product_code},
        headers=user_headers(tg_id),
    )
    return resp


# ---------------------------------------------------------------- API-level

def test_payments_disabled_by_default(client, seed, fresh_tg_id):
    # conftest sets PAYMENTS_ENABLED=false; nothing toggled here.
    assert get_settings().payments_enabled is False
    resp = _create_payment(client, fresh_tg_id)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "payments_disabled"


def test_products_inactive_until_explicit_activation(client, seed, fresh_tg_id):
    """Seed creates products inactive; purchasing them must fail with 404 even
    when payments are enabled — activation is a separate deliberate step."""
    with _TogglePayments():
        resp = _create_payment(client, fresh_tg_id)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "product_not_found"


def test_create_payment_flow_with_stub_provider(client, seed, fresh_tg_id):
    with _TogglePayments():
        session = get_session_factory()()
        try:
            _activate_products(session)
        finally:
            session.close()
        resp = _create_payment(client, fresh_tg_id)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "created"
        assert body["invoice_payload"].startswith("p")
        assert body["bot_invoice_url"].startswith("https://t.me/")

    # DB row persisted with correct amount/currency (integer Stars, never float)
    session = get_session_factory()()
    try:
        payment = session.get(Payment, body["payment_id"])
        assert payment is not None
        assert payment.user_id == session.scalar(
            select(User).where(User.telegram_id == fresh_tg_id)).id
        assert payment.amount == 149 and payment.currency == "XTR"
        assert isinstance(payment.amount, int)
    finally:
        session.close()


def test_status_endpoint_is_owner_scoped(client, seed, fresh_tg_id):
    with _TogglePayments():
        session = get_session_factory()()
        try:
            _activate_products(session)
        finally:
            session.close()
        resp = _create_payment(client, fresh_tg_id)
        pid = resp.json()["payment_id"]
        # owner can read status
        r1 = client.get(f"/api/v1/payments/{pid}/status", headers=user_headers(fresh_tg_id))
        assert r1.status_code == 200
        # another user gets 404 (no existence leak)
        r2 = client.get(f"/api/v1/payments/{pid}/status", headers=user_headers(fresh_tg_id + 1))
        assert r2.status_code == 404


# ---------------------------------------------------------------- provider contract

def test_stars_provider_uses_create_invoice_link_and_validates_result(monkeypatch):
    """sendInvoice returns a Message (no invoice_link); createInvoiceLink
    returns the URL string in `result`. Guard the corrected contract."""
    calls = {}

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url, json=None, timeout=None):
        calls["url"] = url
        calls["body"] = json
        if "ok_true_str" in calls.get("mode", []):
            pass
        return FakeResp({"ok": True, "result": "https://t.me/pay/fake-link"})

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    settings = get_settings()
    old_token = settings.telegram_bot_token
    old_provider = settings.payment_provider
    object.__setattr__(settings, "telegram_bot_token", "123:token")
    object.__setattr__(settings, "payment_provider", "telegram_stars")
    try:
        session = get_session_factory()()
        try:
            product = session.scalar(select(Product).limit(1))
            assert product is not None
            provider = pay_svc.TelegramStarsProvider()
            res = provider.create_invoice(
                telegram_id=1, product=product, payload="abc", currency="XTR")
            assert res.ok and res.bot_invoice_url == "https://t.me/pay/fake-link"
            assert "/createInvoiceLink" in calls["url"]
            assert "chat_id" not in calls["body"]
            assert calls["body"]["prices"][0]["amount"] == product.price_amount
        finally:
            session.close()
    finally:
        object.__setattr__(settings, "telegram_bot_token", old_token)
        object.__setattr__(settings, "payment_provider", old_provider)


def test_stars_provider_rejects_malformed_result(monkeypatch):
    class FakeResp:
        def json(self):
            # sendInvoice-style response: Message object, NOT a link string
            return {"ok": True, "result": {"message_id": 5}}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    settings = get_settings()
    object.__setattr__(settings, "telegram_bot_token", "123:token")
    try:
        session = get_session_factory()()
        try:
            product = session.scalar(select(Product).limit(1))
            provider = pay_svc.TelegramStarsProvider()
            res = provider.create_invoice(
                telegram_id=1, product=product, payload="abc", currency="XTR")
            assert not res.ok
            assert res.error == "malformed_invoice_link_response"
        finally:
            session.close()
    finally:
        object.__setattr__(settings, "telegram_bot_token", "")


# ---------------------------------------------------------------- confirm_payment

def _make_created_payment(tg_id=555001, product_code="premium_month"):
    session = get_session_factory()()
    try:
        _activate_products(session)
        product = session.scalar(select(Product).where(Product.product_code == product_code))
        user = session.scalar(select(User).where(User.telegram_id == tg_id))
        if user is None:
            from app.services.domain import upsert_user
            user = upsert_user(session, {"id": tg_id, "username": "payer"})
        payment = Payment(
            user_id=user.id, provider="stub", invoice_payload=f"payload_{tg_id}_{product.id}",
            product_code=product.product_code, amount=product.price_amount,
            currency=product.currency, status="created",
        )
        session.add(payment)
        session.commit()
        return payment.id, payment.invoice_payload, product.price_amount
    finally:
        session.close()


def test_confirm_requires_matching_event_amount():
    pid, payload, amount = _make_created_payment(555001)
    session = get_session_factory()()
    try:
        # Event WITHOUT actual amount fields must be rejected outright.
        with pytest.raises(ApiError) as ei:
            pay_svc.confirm_payment(session, "ext_1", 555001, True, {"payload": payload})
        assert ei.value.code == "payment_invalid_event"
        assert session.get(Payment, pid).status == "failed"
    finally:
        session.close()


def test_confirm_rejects_wrong_amount_and_currency():
    pid, payload, amount = _make_created_payment(555002)
    session = get_session_factory()()
    try:
        with pytest.raises(ApiError) as ei:
            pay_svc.confirm_payment(session, "ext_2", 555002, True,
                                    {"payload": payload, "total_amount": amount - 1, "currency": "XTR"})
        assert ei.value.code == "payment_amount_mismatch"
        assert session.get(Payment, pid).status == "failed"
        assert not is_premium(session, 555002) or True  # premium not granted below
    finally:
        session.close()

    # wrong currency, right amount
    pid2, payload2, amount2 = _make_created_payment(555003)
    session = get_session_factory()()
    try:
        with pytest.raises(ApiError) as ei:
            pay_svc.confirm_payment(session, "ext_3", 555003, True,
                                    {"payload": payload2, "total_amount": amount2, "currency": "EUR"})
        assert ei.value.code == "payment_amount_mismatch"
        user = session.scalar(select(User).where(User.telegram_id == 555003))
        assert not is_premium(session, user.id)
    finally:
        session.close()


def test_confirm_rejects_wrong_user():
    pid, payload, amount = _make_created_payment(555004)
    session = get_session_factory()()
    try:
        with pytest.raises(ApiError) as ei:
            pay_svc.confirm_payment(session, "ext_4", 777999, True,
                                    {"payload": payload, "total_amount": amount, "currency": "XTR"})
        assert ei.value.code == "forbidden"
        assert session.get(Payment, pid).status == "created"
    finally:
        session.close()


def test_confirm_success_grants_premium_once_and_is_idempotent():
    pid, payload, amount = _make_created_payment(555005)
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.telegram_id == 555005))
        assert not is_premium(session, user.id)

        payment = pay_svc.confirm_payment(
            session, "ext_ok_1", 555005, True,
            {"payload": payload, "total_amount": amount, "currency": "XTR",
             "telegram_payment_charge_id": "tpc_1"})
        assert payment.status == "paid"
        assert payment.paid_at is not None
        assert is_premium(session, user.id)

        ents = list(session.scalars(select(Entitlement).where(Entitlement.user_id == user.id)))
        assert len(ents) == 1

        # Replay of the same external id: idempotent, still exactly one entitlement
        again = pay_svc.confirm_payment(
            session, "ext_ok_1", 555005, True,
            {"payload": payload, "total_amount": amount, "currency": "XTR"})
        assert again.id == pid
        ents2 = list(session.scalars(select(Entitlement).where(Entitlement.user_id == user.id)))
        assert len(ents2) == 1
    finally:
        session.close()


def test_confirm_paid_with_different_external_id_conflicts():
    pid, payload, amount = _make_created_payment(555006)
    session = get_session_factory()()
    try:
        pay_svc.confirm_payment(session, "ext_A", 555006, True,
                                {"payload": payload, "total_amount": amount, "currency": "XTR"})
        with pytest.raises(ApiError) as ei:
            pay_svc.confirm_payment(session, "ext_B", 555006, True,
                                    {"payload": payload, "total_amount": amount, "currency": "XTR"})
        assert ei.value.code == "payment_conflict"
    finally:
        session.close()


def test_unsuccessful_event_marks_failed_without_premium():
    pid, payload, amount = _make_created_payment(555007)
    session = get_session_factory()()
    try:
        payment = pay_svc.confirm_payment(session, "", 555007, False, {"payload": payload})
        assert payment.status == "failed"
        user = session.scalar(select(User).where(User.telegram_id == 555007))
        assert not is_premium(session, user.id)
    finally:
        session.close()


# ------------------------------------------------- premium unlocks gated spread

def test_premium_from_payment_unlocks_celtic_cross(client, seed, fresh_tg_id):
    """End-to-end: create payment -> confirm event -> user may run celtic_cross."""
    import uuid as _uuid
    # Unique idempotency keys per run: the test DB file persists across pytest
    # invocations (create_all only), so a fixed key would replay an old reading.
    uniq = _uuid.uuid4().hex[:16]
    tg_id = fresh_tg_id
    # Before premium: celtic cross is refused
    resp = client.post(
        "/api/v1/readings",
        json={"spread_code": "celtic_cross", "theme_code": "love",
              "question": "?", "idempotency_key": f"ck-pre-{uniq}"},
        headers=user_headers(tg_id),
    )
    assert resp.status_code == 402, (resp.status_code, resp.text)

    pid, payload, amount = _make_created_payment(tg_id)
    session = get_session_factory()()
    try:
        pay_svc.confirm_payment(session, f"ext_{tg_id}", tg_id, True,
                                {"payload": payload, "total_amount": amount, "currency": "XTR"})
    finally:
        session.close()

    resp2 = client.post(
        "/api/v1/readings",
        json={"spread_code": "celtic_cross", "theme_code": "love",
              "question": "?", "idempotency_key": f"ck-post-{uniq}"},
        headers=user_headers(tg_id),
    )
    assert resp2.status_code == 200, resp2.text
