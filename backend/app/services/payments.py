"""Payments abstraction (spec §14). Disabled by default; Telegram Stars adapter.

Provider-neutral service layer: the API and DB never know about a specific PSP.
The payment provider is injected via an adapter implementing PaymentProvider.
Amounts are integers (Telegram Stars), never floats.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import ApiError
from ..models import Entitlement, Payment, Product, User
from .domain import grant_premium
from .timeutil import utcnow


@dataclass(frozen=True)
class InvoiceResult:
    ok: bool
    bot_invoice_url: str | None = None
    error: str | None = None


class PaymentProvider(Protocol):
    name: str

    def create_invoice(self, *, telegram_id: int, product: Product, payload: str,
                       currency: str) -> InvoiceResult: ...


class TelegramStarsProvider:
    """Creates a Telegram invoice with Stars via Bot API sendMessage.

    Requires TELEGRAM_BOT_TOKEN. In environments without network/token access
    the call fails explicitly — payments stay disabled by default.
    """

    name = "telegram_stars"

    def create_invoice(self, *, telegram_id: int, product: Product, payload: str,
                       currency: str) -> InvoiceResult:
        settings = get_settings()
        if not settings.telegram_bot_token:
            return InvoiceResult(ok=False, error="bot_token_not_configured")
        try:  # pragma: no cover - requires network
            import httpx

            api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
            body = {
                "chat_id": telegram_id,
                "title": product.name,
                "description": product.description or product.name,
                "payload": payload,
                "currency": currency,
                "prices": [{"label": product.name, "amount": product.price_amount}],
            }
            resp = httpx.post(f"{api}/sendInvoice", json=body, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                return InvoiceResult(ok=False, error=str(data.get("description", "provider_error"))[:200])
            url = data["result"].get("invoice_link")
            return InvoiceResult(ok=True, bot_invoice_url=url)
        except Exception as exc:  # pragma: no cover
            return InvoiceResult(ok=False, error=f"provider_unavailable:{type(exc).__name__}")


class StubProvider:
    """Offline/test provider: returns a deterministic fake invoice URL."""

    name = "stub"

    def create_invoice(self, *, telegram_id: int, product: Product, payload: str,
                       currency: str) -> InvoiceResult:
        return InvoiceResult(ok=True, bot_invoice_url=f"https://t.me/{payload}")


def get_provider() -> PaymentProvider:
    settings = get_settings()
    if settings.payment_provider == "stub":
        return StubProvider()
    return TelegramStarsProvider()


def require_enabled() -> None:
    if not get_settings().payments_enabled:
        raise ApiError("payments_disabled", "Оплата временно недоступна", 503)


def active_products(session: Session) -> list[Product]:
    return list(session.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.id)))


def create_payment(session: Session, user: User, product_code: str) -> tuple[Payment, InvoiceResult]:
    require_enabled()
    product = session.scalar(select(Product).where(Product.product_code == product_code))
    if product is None or not product.is_active:
        raise ApiError("product_not_found", "Товар не найден", 404, {"product_code": product_code})
    if product.currency != "XTR" and get_settings().payment_provider == "telegram_stars":
        raise ApiError("product_invalid", "Неподдерживаемая валюта товара", 500)

    payload = f"p{product.id}_u{user.id}_{secrets.token_hex(8)}"[:128]
    payment = Payment(
        user_id=user.id,
        provider=get_settings().payment_provider,
        invoice_payload=payload,
        product_code=product.product_code,
        amount=product.price_amount,
        currency=product.currency,
        status="created",
    )
    session.add(payment)
    session.flush()

    provider = get_provider()
    result = provider.create_invoice(
        telegram_id=user.telegram_id, product=product, payload=payload, currency=product.currency
    )
    if not result.ok:
        payment.status = "failed"
        payment.raw_provider_data = {"error": result.error}
        session.commit()
        raise ApiError("payment_failed", "Не удалось создать счёт", 502, {"reason": result.error})
    session.commit()
    return payment, result


def confirm_payment(session: Session, external_payment_id: str, telegram_id: int,
                    successful: bool, raw: dict | None = None) -> Payment:
    """Idempotent confirmation driven by pre_checkout_query / successful_payment.

    Only Telegram-verified events may confirm; amounts must match the product.
    """
    stmt = select(Payment).where(Payment.invoice_payload.is_not(None))
    # Find payment by telegram payload embedded in provider data
    payment: Payment | None = None
    if raw and raw.get("payload"):
        payment = session.scalar(select(Payment).where(Payment.invoice_payload == raw["payload"]))
    if payment is None and external_payment_id:
        payment = session.scalar(select(Payment).where(Payment.external_payment_id == external_payment_id))
    if payment is None:
        raise ApiError("payment_not_found", "Платёж не найден", 404)

    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or user.id != payment.user_id:
        raise ApiError("forbidden", "Несовпадение пользователя платежа", 403)

    if payment.status == "paid":
        return payment  # idempotent replay

    if not successful:
        payment.status = "failed"
        payment.raw_provider_data = raw or {}
        session.commit()
        return payment

    product = session.scalar(select(Product).where(Product.product_code == payment.product_code))
    if product is None or product.price_amount != payment.amount:
        payment.status = "failed"
        payment.raw_provider_data = {**(raw or {}), "error": "amount_mismatch"}
        session.commit()
        raise ApiError("payment_amount_mismatch", "Расхождение суммы платежа", 500)

    payment.status = "paid"
    payment.paid_at = utcnow()
    payment.external_payment_id = external_payment_id or payment.external_payment_id
    payment.raw_provider_data = raw or {}
    grant_premium(
        session,
        user_id=user.id,
        duration_days=product.duration_days,
        source="telegram_stars",
        external_payment_id=external_payment_id or payment.invoice_payload,
    )
    session.commit()
    return payment
