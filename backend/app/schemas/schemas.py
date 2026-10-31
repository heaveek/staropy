"""Pydantic schemas for the REST API (spec §11)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- requests

class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=8192, alias="initData")

    model_config = ConfigDict(populate_by_name=True)


class DevAuthRequest(BaseModel):
    """Development-only auth. Rejected unless ALLOW_DEV_AUTH and non-production."""
    telegram_id: int = Field(gt=0)
    username: str | None = Field(default=None, max_length=64)
    first_name: str | None = Field(default=None, max_length=128)


class PreferencesPatch(BaseModel):
    daily_reminder_enabled: bool | None = None
    subscription_reminder_enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)


class ReadingCreateRequest(BaseModel):
    spread_code: str = Field(min_length=1, max_length=32)
    theme_code: str = Field(min_length=1, max_length=32)
    question: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=64, alias="idempotencyKey")

    model_config = ConfigDict(populate_by_name=True)


class PaymentCreateRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=48)


class InternalPaymentEventRequest(BaseModel):
    """Payment event forwarded by the trusted bot after Telegram verification."""
    telegram_id: int = Field(gt=0)
    external_payment_id: str = Field(min_length=1, max_length=128)
    total_amount: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=8)
    invoice_payload: str = Field(min_length=1, max_length=128)
    successful: bool = True
    provider: str | None = Field(default=None, max_length=24)


# ---------------------------------------------------------------- responses

class OkResponse(BaseModel):
    ok: bool = True


class ThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name_ru: str
    description: str | None = None
    sort_order: int


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int
    code: str
    name_ru: str
    description: str | None = None


class SpreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name_ru: str
    description: str | None = None
    card_count: int
    is_premium: bool
    positions: list[PositionOut]


class CatalogOut(BaseModel):
    themes: list[ThemeOut]
    spreads: list[SpreadOut]
    question_max_length: int


class QuotaOut(BaseModel):
    free_readings_per_day: int
    free_readings_used_today: int
    free_readings_remaining: int
    resets_at_timezone: str


class PremiumStatusOut(BaseModel):
    is_premium: bool
    active_until: datetime | None = None


class MeOut(BaseModel):
    user_id: int
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    is_blocked: bool
    premium: PremiumStatusOut
    quota: QuotaOut
    history_limit: int | None = None  # None => unlimited (premium)
    preferences: "PreferencesOut"


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    daily_reminder_enabled: bool
    subscription_reminder_enabled: bool
    timezone: str | None = None


MeOut.model_rebuild()


class ReadingCardOut(BaseModel):
    position_number: int
    position_code: str
    position_name: str
    card_id: int
    card_code: str
    card_name_ru: str
    orientation: str
    rendered_text: str


class ReadingSummaryItem(BaseModel):
    reading_id: uuid.UUID
    created_at: datetime
    spread_code: str
    spread_name: str
    theme_code: str
    theme_name: str
    summary_text: str
    card_names: list[str]


class ReadingDetailOut(BaseModel):
    reading_id: uuid.UUID
    created_at: datetime
    content_version: str
    is_free: bool
    spread_code: str
    spread_name: str
    theme_code: str
    theme_name: str
    question: str | None
    cards: list[ReadingCardOut]
    opening: str | None
    summary: str
    combinations: list[str]
    advice: str | None
    disclaimer: str
    snapshot: dict


class HistoryOut(BaseModel):
    items: list[ReadingSummaryItem]
    next_cursor: str | None = None
    limited_by_plan: bool = False


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_code: str
    name: str
    description: str | None
    entitlement_type: str
    duration_days: int | None
    price_amount: int
    currency: str


class ProductsOut(BaseModel):
    payments_enabled: bool
    provider: str
    products: list[ProductOut]


# Alias kept for the /premium/products contract (spec §11): same payload shape,
# explicit premium naming so routes and clients share one schema.
PremiumProductsOut = ProductsOut


class PaymentCreateOut(BaseModel):
    payment_id: int
    status: str
    invoice_payload: str
    bot_invoice_url: str | None = None
    message: str | None = None


class PaymentStatusOut(BaseModel):
    payment_id: int
    status: str
    product_code: str
    amount: int
    currency: str
    created_at: datetime
    paid_at: datetime | None = None
