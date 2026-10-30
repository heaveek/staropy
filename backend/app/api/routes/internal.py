"""Internal API for trusted server-side callers (the Telegram bot).

Spec §14: payment confirmation must be driven by authenticated Telegram
updates handled server-side, never by Mini App client messages. The bot
forwards fields extracted from a verified `successful_payment` object; this
endpoint authenticates the caller with a shared-secret HMAC over the exact
request body and then delegates to the idempotent confirm_payment service.

Security model:
  - signature = HMAC-SHA256(secret, raw request body), header X-Internal-Signature;
  - constant-time comparison;
  - fail-closed: an unconfigured secret rejects everything (503) rather than
    silently disabling authentication;
  - replay of the same event is safe (confirm_payment is idempotent by
    external_payment_id);
  - no secrets or amounts are logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from ...config import get_settings
from ...core.errors import ApiError
from ...db.session import get_db
from ...schemas.schemas import InternalPaymentEventRequest, PaymentStatusOut
from ...services.payments import confirm_payment

router = APIRouter(prefix="/internal", tags=["internal"])


def verify_internal_signature(body: bytes, signature: str | None) -> None:
    """Raise ApiError unless `signature` is a valid HMAC of `body`."""
    settings = get_settings()
    secret = settings.internal_api_secret
    if not secret:
        # Fail closed: internal endpoints are unusable without a configured secret.
        raise ApiError("unavailable", "Внутренний API не настроен", 503)
    if not signature:
        raise ApiError("unauthorized", "Требуется подпись внутреннего запроса", 401)
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature.strip().lower()
    if not hmac.compare_digest(computed, provided):
        raise ApiError("unauthorized", "Некорректная подпись внутреннего запроса", 401)


@router.post("/payment-events")
async def payment_event(
    request: Request,
    x_internal_signature: str | None = Header(default=None, alias="X-Internal-Signature"),
    session: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    verify_internal_signature(raw_body, x_internal_signature)

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("validation_failed", "Тело запроса должно быть корректным JSON", 422)

    try:
        event = InternalPaymentEventRequest.model_validate(data)
    except Exception:
        raise ApiError("validation_failed", "Некорректный формат события платежа", 422)

    if not event.successful:
        # A failed/cancelled notification: record it but never grant Premium.
        raise ApiError("payment_not_successful", "Платёж не подтверждён провайдером", 400)

    provider = event.provider or "telegram_stars"
    payment = confirm_payment(
        session,
        external_payment_id=event.external_payment_id,
        telegram_id=event.telegram_id,
        successful=True,
        raw={
            "payload": event.invoice_payload,
            "total_amount": event.total_amount,
            "currency": event.currency,
            "provider": provider,
            "telegram_payment_charge_id": event.external_payment_id,
        },
    )
    return PaymentStatusOut(
        payment_id=payment.id, status=payment.status, product_code=payment.product_code,
        amount=payment.amount, currency=payment.currency,
        created_at=payment.created_at, paid_at=payment.paid_at,
    ).model_dump()
