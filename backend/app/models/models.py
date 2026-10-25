"""ORM models for the tarot mini app. Single coherent schema (spec §10)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, JsonType, TZDateTime, UUIDType
from ..db.types import BigIntPK


def _now() -> datetime:
    from ..services.timeutil import utcnow
    return utcnow()


# ---------------------------------------------------------------- users

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    daily_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)


# ---------------------------------------------------------------- content

class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TagCategory(Base):
    __tablename__ = "tag_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(96), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("tag_categories.id"))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # stable 1..78
    arcana: Mapped[str] = mapped_column(String(8), nullable=False)  # major | minor
    suit: Mapped[str | None] = mapped_column(String(16))  # NULL for major
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(96), nullable=False)
    name_en: Mapped[str] = mapped_column(String(96), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)


class CardTag(Base):
    __tablename__ = "card_tags"
    __table_args__ = (UniqueConstraint("card_id", "tag_id", name="uq_card_tag"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    weight: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default="editorial", nullable=False)  # editorial|generated
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


class CardMeaning(Base):
    __tablename__ = "card_meanings"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"))
    meaning_type: Mapped[str] = mapped_column(String(24), nullable=False, default="general")
    orientation: Mapped[str] = mapped_column(String(8), default="upright", nullable=False)
    text_short: Mapped[str] = mapped_column(Text, nullable=False)
    text_long: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)
    content_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)


class MeaningTag(Base):
    __tablename__ = "meaning_tags"
    __table_args__ = (UniqueConstraint("meaning_id", "tag_id", name="uq_meaning_tag"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    meaning_id: Mapped[int] = mapped_column(ForeignKey("card_meanings.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True)
    weight: Mapped[int | None] = mapped_column(Integer)


RELATION_TYPES = (
    "supports", "weakens", "opposite", "similar", "develops_into",
    "blocks", "complements", "warns_about", "transforms", "amplifies",
)


class CardRelation(Base):
    __tablename__ = "card_relations"
    __table_args__ = (
        UniqueConstraint("source_card_id", "target_card_id", "relation_type", name="uq_card_relation"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    source_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    target_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    strength: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # 1..10
    is_directional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"))
    interpretation_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="editorial", nullable=False)
    editorial_note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


class CardCombination(Base):
    __tablename__ = "card_combinations"
    __table_args__ = (
        UniqueConstraint("card_a_id", "card_b_id", "combination_type", "theme_id", name="uq_card_combination"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    card_a_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    card_b_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    combination_type: Mapped[str] = mapped_column(String(24), nullable=False, default="pair")
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_directional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


class InterpretationTemplate(Base):
    __tablename__ = "interpretation_templates"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    spread_id: Mapped[int | None] = mapped_column(ForeignKey("spreads.id"))
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"))
    template_type: Mapped[str] = mapped_column(String(16), nullable=False)  # opening|position|summary|advice|disclaimer
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


class YesNoMeaning(Base):
    __tablename__ = "yes_no_meanings"
    __table_args__ = (
        UniqueConstraint("card_id", "theme_id", name="uq_yes_no_meaning"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    answer: Mapped[str] = mapped_column(String(8), nullable=False)  # yes|no|maybe
    text: Mapped[str] = mapped_column(Text, nullable=False)
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"))
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


# ---------------------------------------------------------------- spreads

class Spread(Base):
    __tablename__ = "spreads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    card_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    positions: Mapped[list["SpreadPosition"]] = relationship(
        back_populates="spread", order_by="SpreadPosition.position_number", cascade="all, delete-orphan"
    )


class SpreadPosition(Base):
    __tablename__ = "spread_positions"
    __table_args__ = (UniqueConstraint("spread_id", "position_number", name="uq_spread_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spread_id: Mapped[int] = mapped_column(ForeignKey("spreads.id", ondelete="CASCADE"), nullable=False, index=True)
    position_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    interpretation_role: Mapped[str] = mapped_column(String(24), nullable=False, default="general")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    spread: Mapped[Spread] = relationship(back_populates="positions")


# ---------------------------------------------------------------- readings

class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    spread_id: Mapped[int] = mapped_column(ForeignKey("spreads.id"), nullable=False)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id"), nullable=False)
    question: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False, index=True)
    content_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_reading_idempotency"),
    )

    cards: Mapped[list["ReadingCard"]] = relationship(
        back_populates="reading", order_by="ReadingCard.position_number", cascade="all, delete-orphan"
    )


class ReadingCard(Base):
    __tablename__ = "reading_cards"
    __table_args__ = (UniqueConstraint("reading_id", "position_number", name="uq_reading_position"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    reading_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readings.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("spread_positions.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    position_number: Mapped[int] = mapped_column(Integer, nullable=False)
    orientation: Mapped[str] = mapped_column(String(8), default="upright", nullable=False)
    selected_meaning_id: Mapped[int | None] = mapped_column(ForeignKey("card_meanings.id"))
    combination_ids: Mapped[list | None] = mapped_column(JsonType)
    role_meaning_id: Mapped[int | None] = mapped_column(ForeignKey("card_meanings.id"))
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)

    reading: Mapped[Reading] = relationship(back_populates="cards")
    card: Mapped[Card] = relationship(foreign_keys=[card_id])
    position: Mapped[SpreadPosition] = relationship(foreign_keys=[position_id])


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_daily_usage"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    free_readings_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)


# ---------------------------------------------------------------- premium / payments

class Entitlement(Base):
    __tablename__ = "entitlements"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entitlement_type: Mapped[str] = mapped_column(String(32), nullable=False, default="premium")
    starts_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="telegram_stars")  # telegram_stars|admin|promo
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|expired|revoked
    external_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entitlement_type: Mapped[str] = mapped_column(String(32), nullable=False, default="premium")
    duration_days: Mapped[int | None] = mapped_column(Integer)  # NULL => perpetual
    price_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # integer amount, never float
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="XTR")  # XTR = Telegram Stars
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, default="telegram_stars")
    external_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    invoice_payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    product_code: Mapped[str] = mapped_column(String(48), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created")
    raw_provider_data: Mapped[dict | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now, onupdate=_now, nullable=False)
