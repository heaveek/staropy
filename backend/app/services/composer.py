"""Deterministic text composer (spec §9.5).

Composer is pure: same inputs => same outputs, no LLM at runtime. It renders
pre-written editorial blocks into the final reading text and produces the
snapshot consumed by the frontend.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import ApiError
from ..models import Card, InterpretationTemplate, Spread, Theme, User
from . import combinations as combos
from .content_selector import select_position_meaning, select_yes_no
from .rng import draw_cards
from .timeutil import utcnow

DISCLAIMER_DEFAULT = (
    "Расклад носит развлекательно-рефлексивный характер и не является медицинским, "
    "юридическим или финансовым советом."
)


@dataclass
class PositionResult:
    position_number: int
    position_id: int
    position_code: str
    position_name: str
    card_id: int
    card_code: str
    card_name_ru: str
    orientation: str
    meaning_source: str
    selected_meaning_id: int | None
    rendered_text: str


@dataclass
class ComposedReading:
    spread: Spread
    theme: Theme
    question: str | None
    positions: list[PositionResult]
    opening: str
    summary: str
    combination_texts: list[str]
    combination_ids: list[int]
    advice: str | None
    yes_no_answer: str | None
    disclaimer: str
    content_version: str = "v1"

    def snapshot(self, reading_id: _uuid.UUID, created_at) -> dict:
        return {
            "reading_id": str(reading_id),
            "created_at": created_at.isoformat(),
            "content_version": self.content_version,
            "spread": {"code": self.spread.code, "name_ru": self.spread.name_ru},
            "theme": {"code": self.theme.code, "name_ru": self.theme.name_ru},
            "question": self.question,
            "yes_no_answer": self.yes_no_answer,
            "opening": self.opening,
            "positions": [
                {
                    "position_number": p.position_number,
                    "position_code": p.position_code,
                    "position_name": p.position_name,
                    "card_id": p.card_id,
                    "card_code": p.card_code,
                    "card_name_ru": p.card_name_ru,
                    "orientation": p.orientation,
                    "meaning_source": p.meaning_source,
                    "rendered_text": p.rendered_text,
                }
                for p in self.positions
            ],
            "combinations": self.combination_texts,
            "summary": self.summary,
            "advice": self.advice,
            "disclaimer": self.disclaimer,
        }


def _pick_template(session: Session, spread_id: int, theme_id: int, template_type: str) -> str | None:
    """Theme+spread specific first; then theme; then generic approved block."""
    stmt = (
        select(InterpretationTemplate)
        .where(
            InterpretationTemplate.template_type == template_type,
            InterpretationTemplate.is_active.is_(True),
            InterpretationTemplate.review_status == "approved",
        )
        .order_by(InterpretationTemplate.priority.desc(), InterpretationTemplate.id.asc())
    )
    rows = list(session.scalars(stmt))
    exact = [r for r in rows if r.spread_id == spread_id and r.theme_id == theme_id]
    themed = [r for r in rows if r.spread_id is None and r.theme_id == theme_id]
    generic = [r for r in rows if r.spread_id is None and r.theme_id is None]
    for group in (exact, themed, generic):
        if group:
            return group[0].template_text
    return None


def compose_reading(
    session: Session,
    user: User,
    spread: Spread,
    theme: Theme,
    question: str | None,
) -> ComposedReading:
    settings = get_settings()
    if question is not None:
        question = question.strip() or None
        if question and len(question) > settings.question_max_length:
            raise ApiError(
                "question_too_long",
                f"Вопрос длиннее {settings.question_max_length} символов",
                422,
                {"max_length": settings.question_max_length},
            )

    deck = list(session.scalars(select(Card.id).where(Card.is_active.is_(True)).order_by(Card.id)))
    if len(deck) < spread.card_count:
        raise ApiError("content_not_seeded", "Контент колоды не загружен", 503)

    drawn = draw_cards(deck, spread.card_count)

    positions_sorted = sorted(spread.positions, key=lambda p: p.position_number)
    if len(positions_sorted) != spread.card_count:
        raise ApiError("content_invalid", "Конфигурация расклада повреждена", 503)

    card_cache: dict[int, Card] = {}
    results: list[PositionResult] = []
    yes_no_answer: str | None = None

    for pos, (card_id, orientation) in zip(positions_sorted, drawn):
        card = card_cache.get(card_id)
        if card is None:
            card = session.get(Card, card_id)
            if card is None or not card.is_active:
                raise ApiError("content_invalid", "Карта недоступна", 503)
            card_cache[card_id] = card

        if spread.code == "yes_no":
            yn = select_yes_no(session, card.id, theme.id)
            if yn is None:
                # deterministic fallback keeps answer non-empty
                sel = select_position_meaning(session, card.id, orientation, theme.id, pos)
                rendered = f"Скорее всего — «возможно». {sel.text}"
                meaning_id, source = sel.meaning_id, "yes_no"
                yes_no_answer = "maybe"
            else:
                answer, text = yn
                label = {"yes": "Да", "no": "Нет", "maybe": "Возможно"}[answer]
                rendered = f"{label}. {text}"
                meaning_id, source = None, "yes_no"
                yes_no_answer = answer
        else:
            sel = select_position_meaning(session, card.id, orientation, theme.id, pos)
            prefix = f"{pos.name_ru}: " if spread.code != "daily_card" else ""
            orient_note = " (перевёрнутое положение)" if orientation == "reversed" else ""
            rendered = f"{prefix}{sel.text}{orient_note}".strip()
            meaning_id, source = sel.meaning_id, sel.source

        results.append(PositionResult(
            position_number=pos.position_number,
            position_id=pos.id,
            position_code=pos.code,
            position_name=pos.name_ru,
            card_id=card.id,
            card_code=card.code,
            card_name_ru=card.name_ru,
            orientation=orientation,
            meaning_source=source,
            selected_meaning_id=meaning_id,
            rendered_text=rendered,
        ))

    drawn_ids = [r.card_id for r in results]
    combo_rows = combos.find_combinations(session, drawn_ids, theme.id)
    combination_texts = [c.text for c in combo_rows]
    combination_ids = [c.id for c in combo_rows]

    opening = _pick_template(session, spread.id, theme.id, "opening") or (
        f"Расклад «{spread.name_ru}» на тему «{theme.name_ru}»."
    )
    summary = _pick_template(session, spread.id, theme.id, "summary") or _default_summary(results)
    advice = _pick_template(session, spread.id, theme.id, "advice")
    disclaimer = _pick_template(session, spread.id, theme.id, "disclaimer") or DISCLAIMER_DEFAULT

    return ComposedReading(
        spread=spread,
        theme=theme,
        question=question,
        positions=results,
        opening=opening,
        summary=summary,
        combination_texts=combination_texts,
        combination_ids=combination_ids,
        advice=advice,
        yes_no_answer=yes_no_answer,
        disclaimer=disclaimer,
    )


def _default_summary(positions: list[PositionResult]) -> str:
    names = ", ".join(p.card_name_ru for p in positions)
    return f"Выпавшие карты — {names}. Вернитесь к позиции, которая отозвалась сильнее всего."
