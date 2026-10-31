"""Readings endpoints (spec §11.2): create / detail / history."""
from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...core.errors import ApiError
from ...db.session import get_db
from ...models import Reading, Spread, Theme, User
from ...schemas.schemas import (
    HistoryOut, ReadingCardOut, ReadingCreateRequest, ReadingDetailOut, ReadingSummaryItem,
)
from ...services.domain import create_reading, is_premium
from ...services.timeutil import utcnow
from ..deps import get_current_user

router = APIRouter(prefix="/readings", tags=["readings"])


@router.post("")
def create(
    body: ReadingCreateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    reading, replayed = create_reading(
        session=session,
        user=user,
        spread_code=body.spread_code,
        theme_code=body.theme_code,
        question=body.question,
        idempotency_key=body.idempotency_key,
    )
    return {"reading_id": str(reading.id), "replayed": replayed}


def _detail_out(session: Session, reading: Reading) -> ReadingDetailOut:
    spread = session.get(Spread, reading.spread_id)
    theme = session.get(Theme, reading.theme_id)
    snap = reading.snapshot_json or {}
    cards_out = [ReadingCardOut(**{
        "position_number": rc.position_number,
        "position_code": rc.position.code,
        "position_name": rc.position.name_ru,
        "card_id": rc.card_id,
        "card_code": rc.card.code,
        "card_name_ru": rc.card.name_ru,
        "orientation": rc.orientation,
        "rendered_text": rc.rendered_text,
    }) for rc in sorted(reading.cards, key=lambda c: c.position_number)]
    return ReadingDetailOut(
        reading_id=reading.id,
        created_at=reading.created_at,
        content_version=reading.content_version,
        is_free=reading.is_free,
        spread_code=spread.code if spread else "",
        spread_name=spread.name_ru if spread else "",
        theme_code=theme.code if theme else "",
        theme_name=theme.name_ru if theme else "",
        question=reading.question,
        cards=cards_out,
        opening=snap.get("opening"),
        summary=snap.get("summary", reading.summary_text),
        combinations=snap.get("combinations", []),
        advice=snap.get("advice"),
        disclaimer=snap.get("disclaimer", ""),
        snapshot=snap,
    )


@router.get("/{reading_id}", response_model=ReadingDetailOut)
def get_reading(
    reading_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReadingDetailOut:
    reading = session.get(Reading, reading_id)
    if reading is None or reading.user_id != user.id:
        raise ApiError("not_found", "Расклад не найден", 404)
    return _detail_out(session, reading)


def _encode_cursor(created_at, rid: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{rid}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, rid = raw.split("|", 1)
        from datetime import datetime
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception:
        raise ApiError("validation_failed", "Некорректный cursor", 422)


@router.get("", response_model=HistoryOut)
def history(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> HistoryOut:
    premium = is_premium(session, user.id)
    # Free plan sees at most FREE_HISTORY_LIMIT readings (backend-owned cap).
    max_visible = None if premium else get_settings().free_history_limit

    stmt = (
        select(Reading)
        .where(Reading.user_id == user.id, Reading.status == "completed")
        .order_by(Reading.created_at.desc(), Reading.id.desc())
    )
    if cursor:
        ts, rid = _decode_cursor(cursor)
        stmt = stmt.where(or_(Reading.created_at < ts,
                              (Reading.created_at == ts) & (Reading.id < rid)))
    rows = list(session.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]

    limited_by_plan = False
    if max_visible is not None:
        total_before_cap = session.scalar(
            select(func.count())
            .select_from(Reading)
            .where(Reading.user_id == user.id, Reading.status == "completed")
        ) or 0
        before = len(rows)
        rows = rows[:max_visible]
        limited_by_plan = has_more or len(rows) != before or total_before_cap > max_visible
        if len(rows) < max_visible:
            has_more = False

    items = []
    for r in rows:
        spread = session.get(Spread, r.spread_id)
        theme = session.get(Theme, r.theme_id)
        snap = r.snapshot_json or {}
        card_names = [p.get("card_name_ru", "") for p in snap.get("positions", [])]
        items.append(ReadingSummaryItem(
            reading_id=r.id, created_at=r.created_at,
            spread_code=spread.code if spread else "", spread_name=spread.name_ru if spread else "",
            theme_code=theme.code if theme else "", theme_name=theme.name_ru if theme else "",
            summary_text=r.summary_text, card_names=card_names,
        ))
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (has_more and rows) else None
    return HistoryOut(items=items, next_cursor=next_cursor, limited_by_plan=limited_by_plan)
