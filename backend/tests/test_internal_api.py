"""Internal payment-events API tests (bot -> backend trust boundary).

Covers spec §14 requirements for the internal endpoint:
  - fail-closed when INTERNAL_API_SECRET is not configured;
  - missing / wrong HMAC signature -> 401 (constant-time verified server-side);
  - valid signed event confirms payment and grants Premium exactly once;
  - replay of the same event is idempotent (no double entitlement);
  - amount/currency/user/payload mismatches are rejected with 4xx;
  - successful=false never grants Premium.

No real Telegram token or network is required.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_session_factory
from app.models import Entitlement, Payment, Product, User
from app.services.domain import is_premium

from tests.conftest import internal_headers, sign_internal, user_headers
from tests.test_payments import _SettingsPatcher, _TogglePayments, _activate_products


def _event(tg_id: int, payload: str, *, external_id: str = "chg_test_1",
           amount: int = 149, currency: str = "XTR", successful: bool = True) -> dict:
    return {
        "telegram_id": tg_id,
        "external_payment_id": external_id,
        "total_amount": amount,
        "currency": currency,
        "invoice_payload": payload,
        "successful": successful,
    }


def _post_event(client, event: dict, secret: str | None = None):
    body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if secret is None:
        headers = internal_headers(body)
    else:
        headers = {"Content-Type": "application/json",
                   "X-Internal-Signature": sign_internal(body, secret)}
    return client.post("/api/v1/internal/payment-events", content=body, headers=headers)


@pytest.fixture()
def paid_invoice(client, seed, fresh_tg_id):
    """Create a pending payment through the normal API and return (tg_id, payload)."""
    with _TogglePayments():
        session = get_session_factory()()
        try:
            _activate_products(session)
        finally:
            session.close()
        resp = client.post("/api/v1/payments/create",
                           json={"product_code": "premium_month"},
                           headers=user_headers(fresh_tg_id))
        assert resp.status_code == 200, resp.text
        return fresh_tg_id, resp.json()["invoice_payload"]


# ---------------------------------------------------------------- auth layer

def test_internal_api_fail_closed_without_secret(client, paid_invoice):
    tg_id, payload = paid_invoice
    with _SettingsPatcher(internal_api_secret=""):
        resp = _post_event(client, _event(tg_id, payload))
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "unavailable"


def test_internal_api_requires_signature(client, paid_invoice):
    tg_id, payload = paid_invoice
    body = json.dumps(_event(tg_id, payload), separators=(",", ":"), sort_keys=True).encode()
    resp = client.post("/api/v1/internal/payment-events", content=body,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 401


def test_internal_api_rejects_wrong_signature(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id, payload), secret="wrong-secret")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_internal_api_rejects_signature_over_different_body(client, paid_invoice):
    """Signature must cover the exact bytes sent (no tampering after signing)."""
    tg_id, payload = paid_invoice
    event = _event(tg_id, payload)
    good_body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
    sig = sign_internal(good_body)
    # attacker changes the amount but reuses the old signature
    event["total_amount"] = 1
    tampered = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
    resp = client.post("/api/v1/internal/payment-events", content=tampered,
                       headers={"Content-Type": "application/json",
                                "X-Internal-Signature": sig})
    assert resp.status_code == 401


# ---------------------------------------------------------------- happy path

def test_valid_event_confirms_payment_and_grants_premium(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id, payload))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paid"

    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.telegram_id == tg_id))
        assert is_premium(session, user.id) is True
        ent_count = len(list(session.scalars(
            select(Entitlement).where(Entitlement.user_id == user.id))))
        assert ent_count == 1
    finally:
        session.close()


def test_replay_same_event_is_idempotent(client, paid_invoice):
    tg_id, payload = paid_invoice
    event = _event(tg_id, payload)
    r1 = _post_event(client, event)
    r2 = _post_event(client, event)  # Telegram redelivery
    assert r1.status_code == 200 and r2.status_code == 200
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.telegram_id == tg_id))
        ents = list(session.scalars(select(Entitlement).where(Entitlement.user_id == user.id)))
        assert len(ents) == 1  # never double-granted
    finally:
        session.close()


# ---------------------------------------------------------------- validation

def test_amount_mismatch_rejected_no_premium(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id, payload, amount=1))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "payment_amount_mismatch"
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.telegram_id == tg_id))
        assert is_premium(session, user.id) is False
        payment = session.scalar(select(Payment).where(Payment.invoice_payload == payload))
        assert payment.status == "failed"
    finally:
        session.close()


def test_currency_mismatch_rejected(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id, payload, currency="USD"))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "payment_amount_mismatch"


def test_wrong_user_rejected(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id + 777, payload))
    assert resp.status_code in (403, 404)


def test_unknown_payload_rejected(client, seed, fresh_tg_id):
    resp = _post_event(client, _event(fresh_tg_id, "p_nonexistent_payload"))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "payment_not_found"


def test_missing_event_amount_rejected(client, paid_invoice):
    """A signed event without total_amount must fail — no blind confirmation."""
    tg_id, payload = paid_invoice
    event = {"telegram_id": tg_id, "external_payment_id": "chg_x",
             "total_amount": 0, "currency": "XTR",
             "invoice_payload": payload, "successful": True}
    resp = _post_event(client, event)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "payment_amount_mismatch"


def test_unsuccessful_event_never_grants_premium(client, paid_invoice):
    tg_id, payload = paid_invoice
    resp = _post_event(client, _event(tg_id, payload, successful=False))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "payment_not_successful"
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.telegram_id == tg_id))
        assert is_premium(session, user.id) is False
    finally:
        session.close()


def test_duplicate_external_id_on_paid_invoice_rejected(client, paid_invoice):
    tg_id, payload = paid_invoice
    r1 = _post_event(client, _event(tg_id, payload, external_id="chg_a"))
    assert r1.status_code == 200
    r2 = _post_event(client, _event(tg_id, payload, external_id="chg_b"))
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "payment_conflict"
