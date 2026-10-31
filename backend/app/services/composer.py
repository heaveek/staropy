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
from ..models import Card, CardTag, InterpretationTemplate, Spread, Tag, Theme, User
from ..tarot_content.advice import (
    GENERIC_ADVICE_FRAME,
    POSITION_ROLE_FRAMES,
    THEME_ADVICE_FRAMES,
    select_tag_advice,
)
from . import combinations as combos
from .content_selector import select_position_meaning, select_yes_no
from .rng import draw_cards
from .timeutil import utcnow

DISCLAIMER_DEFAULT = (
    "Расклад носит развлекательно-рефлексивный характер и не является медицинским, "
    "юридическим или финансовым советом."
)

UNIVERSAL_ADVICE_TEXT = (
    "Выберите одно маленькое действие, которое зависит только от вас, "
    "и сделайте его сегодня."
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
    interpretation_role: str = "general"


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
            interpretation_role=pos.interpretation_role,
        ))

    drawn_ids = [r.card_id for r in results]
    combo_rows = combos.find_combinations(session, drawn_ids, theme.id)
    combination_texts = [c.text for c in combo_rows]
    combination_ids = [c.id for c in combo_rows]

    opening = _pick_template(session, spread.id, theme.id, "opening") or (
        f"Расклад «{spread.name_ru}» на тему «{theme.name_ru}»."
    )
    summary = _pick_template(session, spread.id, theme.id, "summary") or _default_summary(results)
    advice = compose_advice(session, results, theme.code, spread.id, theme.id)
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


# ---------------------------------------------------------------- advice

def _card_tags(session: Session, card_id: int) -> set[str]:
    """Approved tag codes of a card. Empty set when tags are not seeded yet."""
    stmt = (
        select(Tag.code)
        .join(CardTag, CardTag.tag_id == Tag.id)
        .where(
            CardTag.card_id == card_id,
            CardTag.review_status == "approved",
            Tag.is_active.is_(True),
        )
        .order_by(CardTag.weight.desc(), CardTag.id.asc())
    )
    return set(session.scalars(stmt))


def _anchor_position(results: list[PositionResult]) -> PositionResult | None:
    """Deterministic anchor for advice: explicit advice-role position first,
    then challenge, resource, outcome/answer, finally the first position."""
    for wanted in ("advice", "challenge", "resource", "outcome", "answer"):
        for r in results:
            if r.interpretation_role == wanted:
                return r
    return results[0] if results else None


def _synth_advice(meaning_text: str, role: str, theme_code: str) -> str:
    frame = THEME_ADVICE_FRAMES.get(theme_code, GENERIC_ADVICE_FRAME)
    text = meaning_text.strip().rstrip(".") + "."
    body = frame.format(meaning=text)
    prefix = POSITION_ROLE_FRAMES.get(role, "")
    return f"{prefix}{body}".strip()


def compose_advice(
    session: Session,
    results: list[PositionResult],
    theme_code: str,
    spread_id: int,
    theme_id: int,
) -> str:
    """Context-dependent advice with a deterministic cascade:

    1. DB template `advice:<card_code>:<theme>` — editorial per-card themed rule;
    2. DB template `advice:<card_code>` — editorial per-card rule;
    3. tag rules from the content table (tags x theme, priority-ranked);
    4. synthesis from the anchor card's selected meaning + position role + theme;
    5. legacy generic template only as a last resort (kept for old content).

    Same inputs always produce the same output; no randomness, no LLM.
    """
    anchor = _anchor_position(results)
    if anchor is None:
        return _legacy_generic_advice(session, spread_id, theme_id)

    # 1/2: editorial per-card rules (themed variant wins over the generic one).
    from ..tarot_content.card_advice import CARD_ADVICE_RULES
    for key in ((anchor.card_code, theme_code), (anchor.card_code, None)):
        text = CARD_ADVICE_RULES.get(key)
        if text is not None:
            return text

    # 3: tag-based rules from the editorial content table.
    tags = _card_tags(session, anchor.card_id)
    if tags:
        match = select_tag_advice(tags, theme_code)
        if match is not None:
            return match[1]

    # 4: meaningful synthesis from the actual selected meaning of the card.
    if anchor.meaning_source != "fallback":
        return _synth_advice(anchor.rendered_text, anchor.interpretation_role, theme_code)

    # 5: last resort — legacy generic template (never the universal stub alone).
    legacy = _pick_template(session, spread_id, theme_id, "advice")
    if legacy and legacy != UNIVERSAL_ADVICE_TEXT:
        return legacy
    return _synth_advice(anchor.rendered_text, anchor.interpretation_role, theme_code)


def _legacy_generic_advice(session: Session, spread_id: int, theme_id: int) -> str:
    legacy = _pick_template(session, spread_id, theme_id, "advice")
    if legacy and legacy != UNIVERSAL_ADVICE_TEXT:
        return legacy
    return "Сведите трактовку к одному проверяемому шагу: выберите позицию, которая отозвалась сильнее всего, и сделайте по ней одно действие сегодня."
