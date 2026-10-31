"""Canonical Rider-Waite-Smith deck: 78 cards with stable IDs (spec 6.1).

IDs: Major 1-22 (1=Fool number=0 ... 22=World number=21),
Wands 23-36, Cups 37-50, Swords 51-64, Pentacles 65-78.
Minor ranks: 1 Ace; 2-10 numeric; 11 Page; 12 Knight; 13 Queen; 14 King.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardDef:
    id: int
    arcana: str  # major | minor
    suit: str | None  # wands/cups/swords/pentacles or None
    number: int
    code: str
    name_ru: str
    name_en: str


MAJOR_ARCANA: list[tuple[str, str]] = [
    ("Шут", "The Fool"),
    ("Маг", "The Magician"),
    ("Верховная Жрица", "The High Priestess"),
    ("Императрица", "The Empress"),
    ("Император", "The Emperor"),
    ("Иерофант", "The Hierophant"),
    ("Влюблённые", "The Lovers"),
    ("Колесница", "The Chariot"),
    ("Сила", "Strength"),
    ("Отшельник", "The Hermit"),
    ("Колесо Фортуны", "Wheel of Fortune"),
    ("Справедливость", "Justice"),
    ("Повешенный", "The Hanged Man"),
    ("Смерть", "Death"),
    ("Умеренность", "Temperance"),
    ("Дьявол", "The Devil"),
    ("Башня", "The Tower"),
    ("Звезда", "The Star"),
    ("Луна", "The Moon"),
    ("Солнце", "The Sun"),
    ("Суд", "Judgement"),
    ("Мир", "The World"),
]

SUITS: list[tuple[str, str, str]] = [
    ("wands", "Жезлы", "Wands"),
    ("cups", "Кубки", "Cups"),
    ("swords", "Мечи", "Swords"),
    ("pentacles", "Пентакли", "Pentacles"),
]

RANK_NAMES_RU: dict[int, str] = {
    1: "Туз", 2: "Двойка", 3: "Тройка", 4: "Четвёрка", 5: "Пятёрка",
    6: "Шестёрка", 7: "Семёрка", 8: "Восьмёрка", 9: "Девятка", 10: "Десятка",
    11: "Паж", 12: "Рыцарь", 13: "Королева", 14: "Король",
}
RANK_NAMES_EN: dict[int, str] = {
    1: "Ace", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
    8: "Eight", 9: "Nine", 10: "Ten", 11: "Page", 12: "Knight", 13: "Queen", 14: "King",
}
RANK_CODES: dict[int, str] = {
    1: "ace", 11: "page", 12: "knight", 13: "queen", 14: "king",
}


def build_cards() -> list[CardDef]:
    cards: list[CardDef] = []
    for i, (ru, en) in enumerate(MAJOR_ARCANA, start=1):
        num = 0 if ru == "Шут" else i - 1
        code = f"major_{num:02d}_{en.lower().replace(' ', '_').replace('the_', '')}"
        cards.append(CardDef(id=i, arcana="major", suit=None, number=num,
                             code=code, name_ru=ru, name_en=en))
    next_id = 23
    for suit, suit_ru, suit_en in SUITS:
        for rank in range(1, 15):
            ru = f"{RANK_NAMES_RU[rank]} {suit_ru}"
            en = f"{RANK_NAMES_EN[rank]} of {suit_en}"
            rank_code = RANK_CODES.get(rank, str(rank))
            code = f"{suit}_{rank_code}"
            cards.append(CardDef(id=next_id, arcana="minor", suit=suit, number=rank,
                                 code=code, name_ru=ru, name_en=en))
            next_id += 1
    return cards


CARDS: list[CardDef] = build_cards()


def validate_cards(cards: list[CardDef] | None = None) -> list[str]:
    """Return a list of structural problems (empty means valid)."""
    problems: list[str] = []
    cards = cards if cards is not None else CARDS
    if len(cards) != 78:
        problems.append(f"expected 78 cards, got {len(cards)}")
    ids = [c.id for c in cards]
    if len(set(ids)) != len(ids):
        problems.append("duplicate card ids")
    codes = [c.code for c in cards]
    if len(set(codes)) != len(codes):
        problems.append("duplicate card codes")
    majors = [c for c in cards if c.arcana == "major"]
    if len(majors) != 22 or [c.id for c in majors] != list(range(1, 23)):
        problems.append("major arcana must be ids 1..22")
    suit_ranges = {"wands": (23, 36), "cups": (37, 50), "swords": (51, 64), "pentacles": (65, 78)}
    for suit, (lo, hi) in suit_ranges.items():
        group = [c for c in cards if c.suit == suit]
        if len(group) != 14:
            problems.append(f"suit {suit}: expected 14 cards, got {len(group)}")
            continue
        if [c.id for c in group] != list(range(lo, hi + 1)):
            problems.append(f"suit {suit}: ids must be {lo}..{hi}")
        if [c.number for c in group] != list(range(1, 15)):
            problems.append(f"suit {suit}: numbers must be 1..14 in order")
    for c in cards:
        if c.arcana == "major" and c.suit is not None:
            problems.append(f"card {c.id}: major must have NULL suit")
        if c.arcana == "minor" and c.suit not in suit_ranges:
            problems.append(f"card {c.id}: invalid minor suit {c.suit!r}")
    fool = next((c for c in cards if c.id == 1), None)
    if fool is None or fool.number != 0:
        problems.append("id 1 must be The Fool with number=0")
    world = next((c for c in cards if c.id == 22), None)
    if world is None or world.number != 21:
        problems.append("id 22 must be The World with number=21")
    return problems
