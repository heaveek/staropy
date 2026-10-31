"""FastAPI dependencies: auth (initData verification), DB session, current user."""
from __future__ import annotations

import json
import logging

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import ApiError
from ..core.security import verify_init_data
from ..db.session import get_db
from ..models import User
from ..services.domain import upsert_user

logger = logging.getLogger("app.auth")


def _unauthorized(reason: str) -> ApiError:
    return ApiError("unauthorized", "Требуется авторизация через Telegram Mini App", 401, {"reason": reason})


def get_current_user(
    authorization: str | None = Header(default=None),
    x_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    session: Session = Depends(get_db),
) -> User:
    settings = get_settings()

    # Development-only escape hatch. Never available in production.
    if settings.dev_auth_allowed and authorization and authorization.startswith("Bearer dev-"):
        try:
            dev_id = int(authorization.removeprefix("Bearer dev-"))
        except ValueError:
            raise _unauthorized("invalid_dev_token")
        user = session.scalar(__import__("sqlalchemy").select(User).where(User.telegram_id == dev_id))
        if user is None:
            user = upsert_user(session, {"id": dev_id, "username": "dev_user", "first_name": "Dev"})
            session.commit()
        if user.is_blocked:
            raise ApiError("forbidden", "Доступ ограничен", 403)
        return user

    init_data = x_init_data
    if not init_data and authorization and authorization.startswith("Bearer tma "):
        init_data = authorization.removeprefix("Bearer tma ")

    if not init_data:
        raise _unauthorized("missing_init_data")

    try:
        fields = verify_init_data(init_data, settings.telegram_bot_token)
    except ValueError as exc:
        logger.info("auth rejected: %s", exc)
        raise _unauthorized(str(exc))

    try:
        payload = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError:
        raise _unauthorized("malformed_user_payload")
    if "id" not in payload:
        raise _unauthorized("missing_user_payload")

    user = upsert_user(session, payload)
    session.commit()
    if user.is_blocked:
        raise ApiError("forbidden", "Доступ ограничен", 403)
    return user
