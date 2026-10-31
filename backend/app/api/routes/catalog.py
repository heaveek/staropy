"""Catalog endpoints (spec §11.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db.session import get_db
from ...models import Spread, Theme
from ...schemas.schemas import CatalogOut, PositionOut, SpreadOut, ThemeOut

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=CatalogOut)
def get_catalog(session: Session = Depends(get_db)) -> CatalogOut:
    settings = get_settings()
    themes = list(session.scalars(
        select(Theme).where(Theme.is_active.is_(True)).order_by(Theme.sort_order, Theme.id)
    ))
    spreads = list(session.scalars(
        select(Spread).where(Spread.is_active.is_(True)).order_by(Spread.sort_order, Spread.id)
    ))
    spread_outs = []
    for s in spreads:
        positions = sorted(s.positions, key=lambda p: p.position_number)
        spread_outs.append(SpreadOut(
            code=s.code, name_ru=s.name_ru, description=s.description,
            card_count=s.card_count, is_premium=s.is_premium,
            positions=[PositionOut(number=p.position_number, code=p.code, name_ru=p.name_ru,
                                   description=p.description) for p in positions],
        ))
    return CatalogOut(
        themes=[ThemeOut.model_validate(t) for t in themes],
        spreads=spread_outs,
        question_max_length=settings.question_max_length,
    )
