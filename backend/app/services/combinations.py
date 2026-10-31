"""Combinations and relations lookup (spec §9.4).

Pair keys are normalized: unordered pairs use sorted card ids, so A+B == B+A
unless the stored relation/combination is explicitly directional.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CardCombination, CardRelation


@dataclass(frozen=True)
class ComboText:
    kind: str  # combination|relation
    text: str
    priority: int
    id: int


def _pair_conditions(a: int, b: int, allow_directional: bool):
    conds = [
        (CardCombination.card_a_id == a) & (CardCombination.card_b_id == b),
        (CardCombination.card_a_id == b) & (CardCombination.card_b_id == a),
    ]
    return conds


def find_combinations(session: Session, card_ids: list[int], theme_id: int | None) -> list[ComboText]:
    """Approved, active combination texts for every pair in the draw."""
    if len(card_ids) < 2:
        return []
    results: list[ComboText] = []
    seen_pairs: set[tuple[int, int]] = set()
    for i in range(len(card_ids)):
        for j in range(i + 1, len(card_ids)):
            a, b = card_ids[i], card_ids[j]
            if (a, b) in seen_pairs:
                continue
            seen_pairs.add((a, b))
            stmt = (
                select(CardCombination)
                .where(
                    CardCombination.is_active.is_(True),
                    CardCombination.review_status == "approved",
                    (
                        ((CardCombination.card_a_id == a) & (CardCombination.card_b_id == b))
                        | ((CardCombination.card_a_id == b) & (CardCombination.card_b_id == a))
                    ),
                )
                .order_by(CardCombination.priority.desc(), CardCombination.id.asc())
            )
            rows = list(session.scalars(stmt))
            theme_row = next((r for r in rows if r.theme_id == theme_id), None)
            generic_row = next((r for r in rows if r.theme_id is None), None)
            chosen = theme_row or generic_row
            if chosen is not None:
                results.append(ComboText("combination", chosen.text, chosen.priority, chosen.id))
    return results


def find_relations(session: Session, source_card_id: int, target_card_id: int,
                   theme_id: int | None) -> list[CardRelation]:
    """Relations between two drawn cards in reading order (source -> target).

    Non-directional relations match both ways; directional only as stored.
    """
    stmt = (
        select(CardRelation)
        .where(
            CardRelation.is_active.is_(True),
            CardRelation.review_status == "approved",
            (
                ((CardRelation.source_card_id == source_card_id) & (CardRelation.target_card_id == target_card_id))
                | (
                    (CardRelation.is_directional.is_(False))
                    & (CardRelation.source_card_id == target_card_id)
                    & (CardRelation.target_card_id == source_card_id)
                )
            ),
        )
        .order_by(CardRelation.strength.desc(), CardRelation.id.asc())
    )
    rows = list(session.scalars(stmt))
    theme_rows = [r for r in rows if r.theme_id == theme_id]
    generic_rows = [r for r in rows if r.theme_id is None]
    return (theme_rows or generic_rows)
