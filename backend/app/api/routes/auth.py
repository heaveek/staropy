"""Auth endpoints (spec §11.2)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...config import get_settings
from ...core.errors import ApiError
from ...core.security import verify_init_data
from ...db.session import get_db
from ...models import User
from ...schemas.schemas import MeOut, OkResponse, TelegramAuthRequest, DevAuthRequest
from ...services.domain import quota_view, active_premium_until, get_preferences, is_premium, upsert_user
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _me_out(session: Session, user: User) -> MeOut:
    settings = get_settings()
    pref = get_preferences(session, user)
    premium = is_premium(session, user.id)
    return MeOut(
        user_id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_blocked=user.is_blocked,
        premium={"is_premium": premium, "active_until": active_premium_until(session, user.id)},
        quota=quota_view(session, user.id),
        history_limit=None if premium else settings.free_history_limit,
        preferences={
            "daily_reminder_enabled": pref.daily_reminder_enabled,
            "subscription_reminder_enabled": pref.subscription_reminder_enabled,
            "timezone": pref.timezone,
        },
    )


@router.post("/telegram")
def auth_telegram(body: TelegramAuthRequest, session: Session = Depends(get_db)) -> dict:
    """Verify initData and return the current user state.

    The raw initData is never logged or stored.
    """
    settings = get_settings()
    try:
        fields = verify_init_data(body.init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise ApiError("unauthorized", "Не удалось проверить сессию Telegram", 401, {"reason": str(exc)})
    try:
        payload = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError:
        raise ApiError("unauthorized", "Некорректная нагрузка пользователя", 401,
                       {"reason": "malformed_user_payload"})
    if "id" not in payload:
        raise ApiError("unauthorized", "Отсутствует данные пользователя", 401,
                       {"reason": "missing_user_payload"})
    user = upsert_user(session, payload)
    session.commit()
    if user.is_blocked:
        raise ApiError("forbidden", "Доступ ограничен", 403)
    return {"token": None, "user": _me_out(session, user).model_dump()}


@router.post("/dev", deprecated=True)
def auth_dev(body: DevAuthRequest, session: Session = Depends(get_db)) -> dict:
    """Development-only login. Disabled unless ALLOW_DEV_AUTH=true and env != production."""
    settings = get_settings()
    if not settings.dev_auth_allowed:
        raise ApiError("not_available", "Dev-авторизация отключена", 404)
    user = upsert_user(session, {
        "id": body.telegram_id,
        "username": body.username or "dev_user",
        "first_name": body.first_name or "Dev",
    })
    session.commit()
    return {"token": f"dev-{user.telegram_id}", "user": _me_out(session, user).model_dump()}


@router.get("/me", response_model=MeOut)
def auth_me(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> MeOut:
    return _me_out(session, user)
