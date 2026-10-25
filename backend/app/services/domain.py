"""Domain services: auth, quota, premium, readings (spec §8.2, §14)."""
from __future__ import annotations

import json
import secrets
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import ApiError
from ..models import (
    DailyUsage, Entitlement, Reading, ReadingCard, Spread, Theme, User, UserPreference,
)
from .composer import ComposedReading, compose_reading
from .timeutil import local_today, utcnow


# ---------------------------------------------------------------- users / auth

def upsert_user(session: Session, tg: dict) -> User:
    """Create/update user from verified Telegram payload."""
    telegram_id = int(tg["id"])
    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        # preference row is created after flush, once the user id exists
    user.username = tg.get("username") or user.username
    user.first_name = tg.get("first_name") or user.first_name
    user.last_name = tg.get("last_name") or user.last_name
    user.language_code = tg.get("language_code") or user.language_code
    user.last_seen_at = utcnow()
    session.flush()
    if session.scalar(select(UserPreference).where(UserPreference.user_id == user.id)) is None:
        session.add(UserPreference(user_id=user.id))
    return user


def get_preferences(session: Session, user: User) -> UserPreference:
    pref = session.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if pref is None:
        pref = UserPreference(user_id=user.id)
        session.add(pref)
        session.flush()
    return pref


# ---------------------------------------------------------------- premium

def active_premium_until(session: Session, user_id: int):
    stmt = (
        select(func.max(Entitlement.expires_at))
        .where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_type == "premium",
            Entitlement.status == "active",
        )
    )
    expires = session.scalar(stmt)
    if expires is not None and expires < utcnow():
        _expire_stale(session, user_id)
        return None
    return expires


def _expire_stale(session: Session, user_id: int) -> None:
    session.execute(
        update(Entitlement)
        .where(
            Entitlement.user_id == user_id,
            Entitlement.status == "active",
            Entitlement.expires_at.is_not(None),
            Entitlement.expires_at < utcnow(),
        )
        .values(status="expired")
    )


def is_premium(session: Session, user_id: int) -> bool:
    _expire_stale(session, user_id)
    stmt = select(Entitlement.id).where(
        Entitlement.user_id == user_id,
        Entitlement.entitlement_type == "premium",
        Entitlement.status == "active",
    ).limit(1)
    return session.scalar(stmt) is not None


def grant_premium(session: Session, user_id: int, duration_days: int | None,
                  source: str, external_payment_id: str | None) -> Entitlement:
    """Idempotent by external payment id; extends the current expiry."""
    if external_payment_id:
        existing = session.scalar(
            select(Entitlement).where(Entitlement.external_payment_id == external_payment_id)
        )
        if existing is not None:
            return existing
    current_until = active_premium_until(session, user_id)
    base = current_until if current_until and current_until > utcnow() else utcnow()
    expires_at = None if duration_days is None else _add_days(base, duration_days)
    ent = Entitlement(
        user_id=user_id,
        entitlement_type="premium",
        starts_at=utcnow(),
        expires_at=expires_at,
        source=source,
        status="active",
        external_payment_id=external_payment_id,
    )
    session.add(ent)
    return ent


def _add_days(dt, days: int):
    from datetime import timedelta
    return dt + timedelta(days=days)


# ---------------------------------------------------------------- quota (backend-owned day boundary)

def get_or_create_usage(session: Session, user_id: int) -> DailyUsage:
    """Return today's usage row, creating it atomically if missing.

    On PostgreSQL a plain INSERT would deadlock the unique-constraint path
    under concurrency, so we catch IntegrityError and refetch; the counter is
    still consumed via a conditional UPDATE (see consume_free_reading).
    """
    today = local_today()
    usage = session.scalar(
        select(DailyUsage).where(DailyUsage.user_id == user_id, DailyUsage.usage_date == today)
    )
    if usage is None:
        try:
            usage = DailyUsage(user_id=user_id, usage_date=today, free_readings_used=0)
            session.add(usage)
            session.flush()
        except IntegrityError:  # concurrent insert — refetch
            session.rollback()
            usage = session.scalar(
                select(DailyUsage).where(DailyUsage.user_id == user_id, DailyUsage.usage_date == today)
            )
    return usage


def history_window_start(premium: bool):
    """Backend-owned visibility window for reading history (spec §2.3).

    Free plan: only the most recent FREE_HISTORY_LIMIT readings are visible.
    Premium: unlimited (returns None). The limit is applied server-side in the
    query, never trusted to the frontend.
    """
    return None if premium else get_settings().free_history_limit


def quota_view(session: Session, user_id: int) -> dict:
    settings = get_settings()
    usage = get_or_create_usage(session, user_id)
    used = usage.free_readings_used
    remaining = max(settings.free_readings_per_day - used, 0)
    return {
        "free_readings_per_day": settings.free_readings_per_day,
        "free_readings_used_today": used,
        "free_readings_remaining": remaining,
        "resets_at_timezone": settings.app_timezone,
    }


def consume_free_reading(session: Session, user_id: int) -> bool:
    """Atomically increment daily counter. Returns False when exhausted."""
    settings = get_settings()
    usage = get_or_create_usage(session, user_id)
    if usage.free_readings_used >= settings.free_readings_per_day:
        return False
    res = session.execute(
        update(DailyUsage)
        .where(
            DailyUsage.id == usage.id,
            DailyUsage.free_readings_used < settings.free_readings_per_day,
        )
        .values(free_readings_used=DailyUsage.free_readings_used + 1)
    )
    if res.rowcount != 1:
        session.rollback()
        return False
    session.flush()
    return True


# ---------------------------------------------------------------- readings

def create_reading(
    session: Session,
    user: User,
    spread_code: str,
    theme_code: str,
    question: str | None,
    idempotency_key: str,
) -> tuple[Reading, bool]:
    """Create a reading. Returns (reading, replayed).

    Business errors:
      forbidden        — blocked user
      premium_required — premium spread without entitlement
      limit_reached    — free quota exhausted
      duplicate_*      — invalid spread/theme codes
    Idempotency: same (user, key) replays the stored reading without consuming quota.
    """
    settings = get_settings()
    if user.is_blocked:
        raise ApiError("forbidden", "Доступ ограничен", 403)

    spread = session.scalar(select(Spread).where(Spread.code == spread_code, Spread.is_active.is_(True)))
    if spread is None:
        raise ApiError("spread_not_found", "Расклад не найден", 404, {"spread_code": spread_code})
    theme = session.scalar(select(Theme).where(Theme.code == theme_code, Theme.is_active.is_(True)))
    if theme is None:
        raise ApiError("theme_not_found", "Тема не найдена", 404, {"theme_code": theme_code})

    # Replay check first — never double-consume quota.
    existing = session.scalar(
        select(Reading).where(Reading.user_id == user.id, Reading.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, True

    premium = is_premium(session, user.id)
    if spread.is_premium and not premium:
        raise ApiError("premium_required", "Расклад доступен в премиум-версии", 402,
                       {"spread_code": spread.code})

    is_free = not premium
    if premium:
        is_free = False
    elif not consume_free_reading(session, user.id):
        raise ApiError("limit_reached", "Бесплатный лимит на сегодня исчерпан", 402,
                       {"free_readings_per_day": settings.free_readings_per_day,
                        "resets_at_timezone": settings.app_timezone})

    composed: ComposedReading = compose_reading(session, user, spread, theme, question)
    reading_id = uuid.uuid4()
    created_at = utcnow()
    snapshot = composed.snapshot(reading_id, created_at)

    reading = Reading(
        id=reading_id,
        user_id=user.id,
        spread_id=spread.id,
        theme_id=theme.id,
        question=composed.question,
        created_at=created_at,
        content_version=composed.content_version,
        is_free=is_free,
        snapshot_json=snapshot,
        summary_text=_summary_line(composed),
        status="completed",
        idempotency_key=idempotency_key,
    )
    session.add(reading)
    session.flush()

    for idx, pos in enumerate(composed.positions):
        rc = ReadingCard(
            reading_id=reading.id,
            position_id=pos.position_id,
            card_id=pos.card_id,
            position_number=pos.position_number,
            orientation=pos.orientation,
            selected_meaning_id=pos.selected_meaning_id,
            combination_ids=composed.combination_ids if idx == 0 else None,
            role_meaning_id=None,
            rendered_text=pos.rendered_text,
        )
        session.add(rc)
    try:
        session.commit()
    except IntegrityError:
        # concurrent request with the same idempotency key: replay winner's row
        session.rollback()
        existing = session.scalar(
            select(Reading).where(Reading.user_id == user.id, Reading.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, True
        raise
    return reading, False


def _summary_line(composed: ComposedReading) -> str:
    if composed.yes_no_answer:
        label = {"yes": "Да", "no": "Нет", "maybe": "Возможно"}[composed.yes_no_answer]
        names = ", ".join(p.card_name_ru for p in composed.positions)
        return f"{label} — {names}"
    names = ", ".join(p.card_name_ru for p in composed.positions)
    return f"{composed.spread.name_ru}: {names}"


def new_idempotency_key() -> str:
    return secrets.token_hex(16)
