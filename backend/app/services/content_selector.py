"""Content selection rules (spec §9.2). Deterministic DB queries only.

Priority order for a card at a given position and theme:
1. active approved meaning of the exact theme matching the position role
2. active approved meaning of the exact theme, general type
3. universal approved meaning matching the position role
4. universal approved meaning, general type
5. neutral fallback naming the card and saying the text is still in preparation

Only `review_status == "approved"` rows are ever returned; needs_review/rejected
content never reaches the user. `priority` is respected inside each tier.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Card, CardMeaning, SpreadPosition, YesNoMeaning


@dataclass(frozen=True)
class SelectedMeaning:
    meaning_id: int | None
    text: str
    source: str  # themed_role|themed|universal_role|universal|fallback
    text_long: str = ""


def _meanings(session: Session, card_id: int, orientation: str) -> list[CardMeaning]:
    stmt = (
        select(CardMeaning)
        .where(
            CardMeaning.card_id == card_id,
            CardMeaning.orientation == orientation,
            CardMeaning.is_active.is_(True),
            CardMeaning.review_status == "approved",
        )
        .order_by(CardMeaning.priority.desc(), CardMeaning.id.asc())
    )
    return list(session.scalars(stmt))


def select_position_meaning(
    session: Session,
    card_id: int,
    orientation: str,
    theme_id: int | None,
    position: SpreadPosition,
) -> SelectedMeaning:
    rows = _meanings(session, card_id, orientation)
    role = position.interpretation_role

    def matches(m: CardMeaning, *, theme: bool, role_type: bool) -> bool:
        if theme and m.theme_id != theme_id:
            return False
        if role_type:
            return m.meaning_type == role and role != "general"
        return m.meaning_type == "general"

    # 1. exact theme + suitable role
    if theme_id is not None:
        for m in rows:
            if matches(m, theme=True, role_type=True):
                return SelectedMeaning(m.id, m.text_short, "themed_role", m.text_long)
        # 2. exact theme + general
        for m in rows:
            if matches(m, theme=True, role_type=False):
                return SelectedMeaning(m.id, m.text_short, "themed", m.text_long)
    # 3. universal + suitable role
    for m in rows:
        if m.theme_id is None and matches(m, theme=False, role_type=True):
            return SelectedMeaning(m.id, m.text_short, "universal_role", m.text_long)
    # 4. universal + general
    for m in rows:
        if m.theme_id is None and matches(m, theme=False, role_type=False):
            return SelectedMeaning(m.id, m.text_short, "universal", m.text_long)

    # Any other approved row beats the neutral fallback (better than nothing).
    if rows:
        return SelectedMeaning(rows[0].id, rows[0].text_short, "universal", rows[0].text_long)

    # 5. neutral fallback: name the card, say the text is being prepared.
    card = session.get(Card, card_id)
    name = card.name_ru if card else f"карта №{card_id}"
    return SelectedMeaning(
        None,
        f"{name}: текст для этого сочетания ещё готовится. "
        "Наблюдайте за ситуацией спокойно и без поспешных решений.",
        "fallback",
    )


def select_yes_no(
    session: Session,
    card_id: int,
    theme_id: int | None,
) -> tuple[str, str] | None:
    """Return (answer, text) for the card, preferring theme-specific rows."""
    stmt = (
        select(YesNoMeaning)
        .where(
            YesNoMeaning.card_id == card_id,
            YesNoMeaning.is_active.is_(True),
            YesNoMeaning.review_status == "approved",
        )
        .order_by(YesNoMeaning.priority.desc(), YesNoMeaning.id.asc())
    )
    rows = list(session.scalars(stmt))
    if theme_id is not None:
        for r in rows:
            if r.theme_id == theme_id:
                return r.answer, r.text
    for r in rows:
        if r.theme_id is None:
            return r.answer, r.text
    return None
