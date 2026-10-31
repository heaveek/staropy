"""Payments & premium endpoints (spec §11, §15).

Spec paths:
  GET  /api/v1/premium/products      — only active tariffs
  GET  /api/v1/premium/status        — entitlement status
  POST /api/v1/payments/create       — invoice with server-side price + unique payload
  GET  /api/v1/payments/{id}/status  — payment status for its owner (+ legacy alias)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config import get_settings
from ...core.errors import ApiError
from ...db.session import get_db
from ...models import Payment, User
from ...schemas.schemas import (
    PaymentCreateOut, PaymentCreateRequest, PaymentStatusOut,
    PremiumProductsOut, PremiumStatusOut, ProductOut, ProductsOut,
)
from ...services.domain import active_premium_until, is_premium
from ...services.payments import active_products, create_payment
from ..deps import get_current_user

premium_router = APIRouter(prefix="/premium", tags=["premium"])
payments_router = APIRouter(prefix="/payments", tags=["payments"])


def _products_payload(session: Session) -> ProductsOut:
    settings = get_settings()
    items = [ProductOut.model_validate(p) for p in active_products(session)]
    return ProductsOut(payments_enabled=settings.payments_enabled,
                       provider=settings.payment_provider, products=items)


@premium_router.get("/products", response_model=PremiumProductsOut)
def premium_products(session: Session = Depends(get_db)) -> ProductsOut:
    """Only real, active tariffs from the backend. Payments never imitated."""
    return _products_payload(session)


@premium_router.get("/status", response_model=PremiumStatusOut)
def premium_status(user: User = Depends(get_current_user),
                   session: Session = Depends(get_db)) -> PremiumStatusOut:
    return PremiumStatusOut(is_premium=is_premium(session, user.id),
                            active_until=active_premium_until(session, user.id))


@payments_router.post("/create")
def pay_create(body: PaymentCreateRequest, user: User = Depends(get_current_user),
               session: Session = Depends(get_db)) -> dict:
    payment, invoice = create_payment(session, user, body.product_code)
    return PaymentCreateOut(
        payment_id=payment.id, status=payment.status, invoice_payload=payment.invoice_payload,
        bot_invoice_url=invoice.bot_invoice_url,
        message="Откройте счёт в Telegram для оплаты" if invoice.ok else None,
    ).model_dump()


@payments_router.get("/{payment_id}", include_in_schema=False)
@payments_router.get("/{payment_id}/status")
def pay_status(payment_id: int, user: User = Depends(get_current_user),
               session: Session = Depends(get_db)) -> dict:
    payment = session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise ApiError("not_found", "Платёж не найден", 404)
    return PaymentStatusOut(
        payment_id=payment.id, status=payment.status, product_code=payment.product_code,
        amount=payment.amount, currency=payment.currency,
        created_at=payment.created_at, paid_at=payment.paid_at,
    ).model_dump()
