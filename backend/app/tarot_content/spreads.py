"""Five spreads and their fixed positions (spec section 7)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionDef:
    number: int
    code: str
    name_ru: str
    description: str
    interpretation_role: str  # general|outcome|advice|challenge|resource|answer


@dataclass(frozen=True)
class SpreadDef:
    code: str
    name_ru: str
    description: str
    is_premium: bool
    sort_order: int
    positions: tuple[PositionDef, ...]

    @property
    def card_count(self) -> int:
        return len(self.positions)


THEMES: list[tuple[str, str, str]] = [
    ("love", "Любовь и отношения", "Близость, партнёрство, чувства"),
    ("work", "Работа и карьера", "Дело, профессии, проекты, коллеги"),
    ("money", "Деньги и ресурсы", "Доходы, расходы, накопления, ценность"),
    ("self_development", "Саморазвитие", "Внутренняя работа, рост, привычки"),
]

SPREADS: list[SpreadDef] = [
    SpreadDef(
        code="daily_card", name_ru="Карта дня",
        description="Одна карта: общий фокус дня, возможность или тема внимания.",
        is_premium=False, sort_order=1,
        positions=(PositionDef(1, "card_of_day", "Карта дня",
                               "Общий фокус, возможность или тема внимания на день.", "general"),),
    ),
    SpreadDef(
        code="yes_no", name_ru="Да / Нет",
        description="Короткий ответ-направление на конкретный вопрос.",
        is_premium=False, sort_order=2,
        positions=(PositionDef(1, "answer", "Ответ",
                               "Редакционный сигнал yes/no/maybe с пояснением.", "answer"),),
    ),
    SpreadDef(
        code="past_present_future", name_ru="Прошлое — Настоящее — Будущее",
        description="Три карты: откуда, где и куда движется ситуация.",
        is_premium=False, sort_order=3,
        positions=(
            PositionDef(1, "past", "Прошлое", "Что уже повлияло на ситуацию.", "resource"),
            PositionDef(2, "present", "Настоящее", "Как обстоят дела сейчас.", "general"),
            PositionDef(3, "future", "Возможное направление развития",
                        "Куда ситуация может двигаться при текущем подходе.", "outcome"),
        ),
    ),
    SpreadDef(
        code="situation_advice_outcome", name_ru="Ситуация — Совет — Итог",
        description="Что происходит, что сделать и к чему это может привести.",
        is_premium=False, sort_order=4,
        positions=(
            PositionDef(1, "situation", "Ситуация", "Как видится ситуация сейчас.", "general"),
            PositionDef(2, "advice", "Совет/действие", "Что стоит учесть или сделать.", "advice"),
            PositionDef(3, "outcome", "Возможный итог",
                        "Что вероятно при сохранении текущего подхода.", "outcome"),
        ),
    ),
    SpreadDef(
        code="celtic_cross", name_ru="Кельтский крест",
        description="Подробный расклад из десяти карт для глубокого разбора ситуации.",
        is_premium=True, sort_order=5,
        positions=(
            PositionDef(1, "present_situation", "Текущая ситуация", "Суть положения сейчас.", "general"),
            PositionDef(2, "challenge", "Препятствие", "Что пересекает и усложняет ситуацию.", "challenge"),
            PositionDef(3, "foundation", "Основание ситуации", "Что лежит в основе.", "resource"),
            PositionDef(4, "recent_past", "Недавнее прошлое", "Что недавно ушло или завершилось.", "resource"),
            PositionDef(5, "conscious_goal", "Осознанная цель", "На что вы сознательно ориентируетесь.", "general"),
            PositionDef(6, "near_future", "Ближайшее развитие", "Что произойдёт в обозримом будущем.", "outcome"),
            PositionDef(7, "self", "Позиция вопрошающего", "Как вы сами участвуете в ситуации.", "general"),
            PositionDef(8, "environment", "Внешние влияния", "Окружение и другие люди.", "general"),
            PositionDef(9, "hopes_fears", "Надежды и опасения", "Что вы хотите или боитесь.", "challenge"),
            PositionDef(10, "outcome", "Возможный итог",
                        "Итог при сохранении текущих тенденций.", "outcome"),
        ),
    ),
]


def validate_spreads() -> list[str]:
    problems: list[str] = []
    codes = [s.code for s in SPREADS]
    if len(set(codes)) != len(codes):
        problems.append("duplicate spread codes")
    expected = {"daily_card": 1, "yes_no": 1, "past_present_future": 3,
                "situation_advice_outcome": 3, "celtic_cross": 10}
    if set(expected) != set(codes):
        problems.append("spread set does not match spec")
    for s in SPREADS:
        if expected.get(s.code) != len(s.positions):
            problems.append(f"spread {s.code}: expected {expected.get(s.code)} positions")
        nums = [p.number for p in s.positions]
        if nums != list(range(1, len(nums) + 1)):
            problems.append(f"spread {s.code}: position numbers must be 1..N")
        pcodes = [p.code for p in s.positions]
        if len(set(pcodes)) != len(pcodes):
            problems.append(f"spread {s.code}: duplicate position codes")
    celtic = next(s for s in SPREADS if s.code == "celtic_cross")
    if not celtic.is_premium:
        problems.append("celtic_cross must be premium")
    return problems
