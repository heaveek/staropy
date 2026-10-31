"""Content seed loader (spec §16.3): idempotent, validation before DB write.

Products are created inactive by default; activation is a separate explicit
step so payments can never be enabled accidentally.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Card, CardCombination, CardMeaning, CardRelation, CardTag, InterpretationTemplate,
    MeaningTag, Payment, Product, Spread, SpreadPosition, Tag, TagCategory, Theme,
    User, YesNoMeaning,
)
from ..tarot_content import cards as card_defs
from ..tarot_content import meanings as meaning_defs
from ..tarot_content import spreads as spread_defs
from ..tarot_content import tags as tag_defs


# Content edition served to users; bumped when editorial texts are reworked.
CONTENT_VERSION = "v2"


@dataclass(frozen=True)
class SeedReport:
    created: dict
    skipped_reasons: list[str]

    def as_dict(self) -> dict:
        return {"created": self.created, "skipped_reasons": self.skipped_reasons}


def validate_content() -> list[str]:
    problems: list[str] = []
    problems += card_defs.validate_cards()
    problems += tag_defs.validate_tags()
    problems += spread_defs.validate_spreads()
    code_set = {c.code for c in card_defs.CARDS}
    tag_set = {t.code for t in tag_defs.TAGS}
    theme_codes = {t[0] for t in spread_defs.THEMES}
    seen_meanings: set[tuple] = set()
    for m in meaning_defs.all_meanings():
        if m.card_code not in code_set:
            problems.append(f"meaning references unknown card {m.card_code}")
        if m.theme is not None and m.theme not in theme_codes:
            problems.append(f"meaning references unknown theme {m.theme}")
        key = (m.card_code, m.theme, m.meaning_type)
        if key in seen_meanings:
            problems.append(f"duplicate meaning definition {key}")
        seen_meanings.add(key)
        if not m.text_short.strip():
            problems.append(f"empty meaning text for {m.card_code}")
    yn_seen: set[tuple] = set()
    for y in meaning_defs.all_yes_no():
        if y.card_code not in code_set:
            problems.append(f"yes_no references unknown card {y.card_code}")
        if y.answer not in {"yes", "no", "maybe"}:
            problems.append(f"yes_no invalid answer {y.answer}")
        key = (y.card_code, y.theme)
        if key in yn_seen:
            problems.append(f"duplicate yes/no definition {key}")
        yn_seen.add(key)
    for ct in meaning_defs.all_card_tags():
        if ct.card_code not in code_set:
            problems.append(f"card_tag references unknown card {ct.card_code}")
        if ct.tag_code not in tag_set:
            problems.append(f"card_tag references unknown tag {ct.tag_code}")
    return problems


# Editorial combinations & relations (approved texts, deterministic ids via unique constraints)
COMBINATIONS: list[tuple[str, str, str | None, str]] = [
    ("major_01_magician", "major_07_chariot", None, "Намерение соединяется с волей: шанс довести задуманное быстрее."),
    ("major_02_high_priestess", "major_18_moon", None, "Двойной знак скрытности: интуиции нужен осторожный пересказ — велик риск самообмана."),
    ("major_06_lovers", "cups_2", None, "Усиление взаимности: выбор сердцем и предложение сердца совпадают."),
    ("major_15_devil", "cups_5", None, "Ощущение ловушки усиливает фокус на потере; разорвать цикл помогает признание схемы."),
    ("major_16_tower", "major_13_death", None, "Двойной знак завершения: старое рухнет и освободит место быстрее обычного."),
    ("major_17_star", "major_19_sun", None, "Надежда встречается с ясностью: один из самых обнадёживающих дуэтов колоды."),
    ("wands_ace", "pentacles_ace", None, "Идея получает материальный шанс: стоит зафиксировать план воплощения."),
    ("swords_7", "cups_7", None, "Иллюзии плюс уклончивость: проверяйте договорённости письменно."),
    ("pentacles_4", "wands_10", None, "Страх потерять и перегрузка вместе: удержание лишнего истощает."),
    ("cups_3", "wands_6", None, "Праздник и признание: публичный успех разделить с близкими."),
    ("major_09_hermit", "swords_4", None, "Двойная пауза: восстановление требует тишины, не решений."),
    ("major_10_wheel_of_fortune", "wands_8", None, "Цикл ускоряется: перемены придут быстрее ожиданий."),
]

RELATIONS: list[tuple[str, str, str, int, bool, str]] = [
    # (source, target, type, strength, directional, interpretation_text)
    ("major_00_fool", "major_21_world", "similar", 6, False, "Начало и завершение цикла зеркальны: в каждом новом старте спрятан итог."),
    ("major_13_death", "major_17_star", "develops_into", 7, True, "Завершение этапа открывает место для тихого восстановления."),
    ("major_16_tower", "major_13_death", "similar", 6, False, "Обе карты о завершении: Башня — внезапно, Смерть — неизбежно."),
    ("major_15_devil", "major_14_temperance", "opposite", 7, False, "Привязанность против умеренности: баланс — антидот зависимости."),
    ("major_18_moon", "major_19_sun", "opposite", 8, False, "Туман и ясность: одна рассекает искажения другой."),
    ("swords_9", "major_17_star", "warns_about", 5, True, "Тревога может затмить надежду; не путуйте страхи с прогнозом."),
    ("wands_10", "major_08_strength", "transforms", 6, True, "Перегруз превращается в силу, когда часть ноши отпущена."),
    ("cups_4", "cups_ace", "blocks", 5, True, "Эмоциональная пресыщенность мешает принять новый импульс чувств."),
    ("major_04_emperor", "major_03_empress", "complements", 7, False, "Порядок и рост дополняют друг друга: структура питает развитие."),
    ("pentacles_7", "wands_8", "weakens", 4, True, "Скорость ослабляет терпеливое ожидание урожая: не дёргайте процесс."),
]

TEMPLATES: list[tuple[str, str | None, str, str, int]] = [
    # (template_type, spread_code|None, theme_code|None, text, priority)
    ("opening", None, None, "Расклад помогает посмотреть на ситуацию с разных сторон. Воспринимайте образы как подсказки для размышления, а не как предписание.", 0),
    ("summary", None, None, "Главное — не отдельная карта, а линия между ними. Отметьте, какая позиция вызвала самый сильный отклик.", 0),
    # Legacy universal stub: kept in the table for old-content compatibility but
    # never served as advice — the composer now builds context-dependent advice
    # from card tags/meanings/positions (see app/tarot_content/advice.py).
    ("advice", None, None, "Выберите одно маленькое действие, которое зависит только от вас, и сделайте его сегодня.", -100),
    ("disclaimer", None, None, "Расклад носит развлекательно-рефлексивный характер и не является медицинским, юридическим или финансовым советом.", 0),
    ("opening", None, "love", "Тема близости: расклад показывает, где между вами течение, а где — сопротивление.", 10),
    ("summary", None, "love", "В отношениях важнее всего разговор: обсудите с партнёром позицию, которая отозвалась сильнее всего.", 10),
    ("opening", None, "work", "Рабочий контекст: расклад разделяет то, что под вашим контролем, и то, что стоит просто учитывать.", 10),
    ("summary", None, "work", "Профессиональные решения любят проверку фактами: сверьтесь с коллегами прежде, чем менять курс.", 10),
    ("opening", None, "money", "Тема ресурсов: расклад подсвечивает привычки обращения с деньгами, а не обещает доход.", 10),
    ("summary", None, "money", "Финансовые шаги требуют расчёта: трактовки здесь — повод задать вопросы, а не основание для сделок.", 10),
    ("opening", None, "self_development", "Разговор с собой: расклад помогает увидеть текущий этап и точку опоры для роста.", 10),
    ("summary", None, "self_development", "Рост измеряется маленькими повторениями: выберите одну практику и держите её две недели.", 10),
    ("position", "past_present_future", None, "Прошлое уже повлияло; задача позиции — показать ресурс или урок, который вы несёте дальше.", 5),
    ("position", "celtic_cross", None, "Кельтский крест читается слоями: сначала центр (позиции 1–2), затем основание и время, затем люди и итог.", 5),
]

PRODUCTS: list[tuple[str, str, str, int | None, int]] = [
    # (product_code, name, description, duration_days, price_stars)
    ("premium_month", "Премиум на месяц", "Все расклады, без лимита бесплатных карт, полная история", 30, 149),
    ("premium_year", "Премиум на год", "Все расклады, без лимита бесплатных карт, полная история", 365, 999),
    ("celtic_single", "Кельтский крест: один доступ", "Разовый доступ к подробному раскладу", None, 49),
]


def load_content(session: Session) -> SeedReport:
    """Idempotent content load. Raises ValueError on invalid content (fail fast)."""
    problems = validate_content()
    if problems:
        raise ValueError("content validation failed: " + "; ".join(problems[:20]))

    created: dict[str, int] = {}
    reasons: list[str] = []

    # themes
    n = 0
    for i, (code, name_ru, desc) in enumerate(spread_defs.THEMES, start=1):
        if session.scalar(select(Theme).where(Theme.code == code)) is None:
            session.add(Theme(code=code, name_ru=name_ru, description=desc, sort_order=i))
            n += 1
    created["themes"] = n

    # tag categories & tags
    n = 0
    for i, cat in enumerate(tag_defs.CATEGORIES, start=1):
        if session.scalar(select(TagCategory).where(TagCategory.code == cat.code)) is None:
            session.add(TagCategory(code=cat.code, name_ru=cat.name_ru,
                                    description=cat.description, sort_order=i))
            n += 1
    created["tag_categories"] = n

    n = 0
    for t in tag_defs.TAGS:
        if session.scalar(select(Tag).where(Tag.code == t.code)) is None:
            cat = session.scalar(select(TagCategory).where(TagCategory.code == t.category))
            session.add(Tag(code=t.code, name_ru=t.name_ru, category_id=cat.id if cat else None))
            n += 1
    created["tags"] = n

    # cards
    n = 0
    for c in card_defs.CARDS:
        if session.scalar(select(Card).where(Card.code == c.code)) is None:
            session.add(Card(id=c.id, arcana=c.arcana, suit=c.suit, number=c.number,
                             code=c.code, name_ru=c.name_ru, name_en=c.name_en,
                             image_url=f"/static/cards/{c.code}.svg"))
            n += 1
    created["cards"] = n

    # card tags
    n = 0
    for ct in meaning_defs.all_card_tags():
        card = session.scalar(select(Card).where(Card.code == ct.card_code))
        tag = session.scalar(select(Tag).where(Tag.code == ct.tag_code))
        if card and tag and session.scalar(
            select(CardTag).where(CardTag.card_id == card.id, CardTag.tag_id == tag.id)
        ) is None:
            session.add(CardTag(card_id=card.id, tag_id=tag.id, weight=ct.weight,
                                source=ct.source, review_status=ct.review_status))
            n += 1
    created["card_tags"] = n

    # meanings
    n = 0
    for m in meaning_defs.all_meanings():
        card = session.scalar(select(Card).where(Card.code == m.card_code))
        theme = session.scalar(select(Theme).where(Theme.code == m.theme)) if m.theme else None
        exists = session.scalar(
            select(CardMeaning).where(
                CardMeaning.card_id == card.id,
                CardMeaning.theme_id == (theme.id if theme else None),
                CardMeaning.meaning_type == m.meaning_type,
                CardMeaning.orientation == "upright",
            )
        )
        if exists is not None and (
            exists.content_version != CONTENT_VERSION
            or m.text_long != exists.text_long
            or m.text_short != exists.text_short
            or m.priority != exists.priority
        ):
            # Editorial refresh (v2): serve the new long-form text without
            # duplicating rows; keeps seeding idempotent for fresh databases.
            exists.text_short = m.text_short
            exists.text_long = m.text_long
            exists.priority = m.priority
            exists.content_version = CONTENT_VERSION
            session.flush()
            continue
        if exists is None:
            # MVP draws upright cards only (spec §8); reversed meanings are not
            # seeded until reversal content is prepared.
            nm = CardMeaning(
                card_id=card.id, theme_id=theme.id if theme else None,
                meaning_type=m.meaning_type, orientation="upright",
                text_short=m.text_short, text_long=m.text_long,
                priority=m.priority, review_status=m.review_status,
                content_version=CONTENT_VERSION,
            )
            session.add(nm)
            session.flush()
            n += 1
    created["card_meanings"] = n

    # yes/no
    n = 0
    for y in meaning_defs.all_yes_no():
        card = session.scalar(select(Card).where(Card.code == y.card_code))
        theme = session.scalar(select(Theme).where(Theme.code == y.theme)) if y.theme else None
        exists = session.scalar(
            select(YesNoMeaning).where(
                YesNoMeaning.card_id == card.id,
                YesNoMeaning.theme_id == (theme.id if theme else None),
            )
        )
        if exists is None:
            session.add(YesNoMeaning(card_id=card.id, answer=y.answer, text=y.text,
                                     theme_id=theme.id if theme else None,
                                     priority=y.priority, review_status=y.review_status))
            n += 1
    created["yes_no_meanings"] = n

    # spreads + positions
    n = 0
    for s in spread_defs.SPREADS:
        spread = session.scalar(select(Spread).where(Spread.code == s.code))
        if spread is None:
            spread = Spread(code=s.code, name_ru=s.name_ru, description=s.description,
                            card_count=s.card_count, is_premium=s.is_premium, sort_order=s.sort_order)
            session.add(spread)
            session.flush()
            n += 1
        for p in s.positions:
            if session.scalar(select(SpreadPosition).where(
                SpreadPosition.spread_id == spread.id, SpreadPosition.position_number == p.number
            )) is None:
                session.add(SpreadPosition(
                    spread_id=spread.id, position_number=p.number, code=p.code,
                    name_ru=p.name_ru, description=p.description,
                    interpretation_role=p.interpretation_role, sort_order=p.number,
                ))
    created["spreads"] = n

    # combinations & relations
    n = 0
    for ca, cb, theme_code, text in COMBINATIONS:
        card_a = session.scalar(select(Card).where(Card.code == ca))
        card_b = session.scalar(select(Card).where(Card.code == cb))
        theme = session.scalar(select(Theme).where(Theme.code == theme_code)) if theme_code else None
        exists = session.scalar(
            select(CardCombination).where(
                ((CardCombination.card_a_id == card_a.id) & (CardCombination.card_b_id == card_b.id))
                | ((CardCombination.card_a_id == card_b.id) & (CardCombination.card_b_id == card_a.id)),
                CardCombination.theme_id == (theme.id if theme else None),
            )
        )
        if exists is None:
            session.add(CardCombination(card_a_id=card_a.id, card_b_id=card_b.id,
                                       combination_type="pair", theme_id=theme.id if theme else None,
                                       text=text, priority=5))
            n += 1
    created["card_combinations"] = n

    n = 0
    for src, tgt, rtype, strength, directional, text in RELATIONS:
        s_card = session.scalar(select(Card).where(Card.code == src))
        t_card = session.scalar(select(Card).where(Card.code == tgt))
        exists = session.scalar(select(CardRelation).where(
            CardRelation.source_card_id == s_card.id,
            CardRelation.target_card_id == t_card.id,
            CardRelation.relation_type == rtype,
        ))
        if exists is None:
            session.add(CardRelation(source_card_id=s_card.id, target_card_id=t_card.id,
                                     relation_type=rtype, strength=strength,
                                     is_directional=directional, interpretation_text=text))
            n += 1
    created["card_relations"] = n

    # templates
    n = 0
    for ttype, spread_code, theme_code, text, prio in TEMPLATES:
        spread = session.scalar(select(Spread).where(Spread.code == spread_code)) if spread_code else None
        theme = session.scalar(select(Theme).where(Theme.code == theme_code)) if theme_code else None
        exists = session.scalar(select(InterpretationTemplate).where(
            InterpretationTemplate.template_type == ttype,
            InterpretationTemplate.spread_id == (spread.id if spread else None),
            InterpretationTemplate.theme_id == (theme.id if theme else None),
        ))
        if exists is None:
            session.add(InterpretationTemplate(template_type=ttype,
                                               spread_id=spread.id if spread else None,
                                               theme_id=theme.id if theme else None,
                                               template_text=text, priority=prio))
            n += 1
    created["interpretation_templates"] = n

    # Per-card editorial advice rules mirrored into the DB with
    # `advice:<card_code>[:<theme>]` keys (composer cascade level 0).
    # Theme scoping lives in the key itself, so rows stay theme_id-agnostic.
    from ..tarot_content.card_advice import CARD_ADVICE_RULES
    n_pc = 0
    for (card_code, theme_code_), adv_text in CARD_ADVICE_RULES.items():
        pc = f"advice:{card_code}" + (f":{theme_code_}" if theme_code_ else "")
        exists_tpl = session.scalar(select(InterpretationTemplate).where(
            InterpretationTemplate.template_type == "advice",
            InterpretationTemplate.position_code == pc,
        ))
        if exists_tpl is None:
            session.add(InterpretationTemplate(
                template_type="advice", spread_id=None, theme_id=None,
                position_code=pc, template_text=adv_text, priority=60,
            ))
            n_pc += 1
        elif exists_tpl.template_text != adv_text:
            exists_tpl.template_text = adv_text
            session.flush()
    created["advice_card_templates"] = n_pc

    # products — inactive by default (activation is an explicit separate step)
    n = 0
    for code, name, desc, days, price in PRODUCTS:
        if session.scalar(select(Product).where(Product.product_code == code)) is None:
            session.add(Product(product_code=code, name=name, description=desc,
                                entitlement_type="premium", duration_days=days,
                                price_amount=price, currency="XTR", is_active=False))
            n += 1
            reasons.append(f"product {code} created INACTIVE — activate explicitly")
    created["products"] = n

    session.commit()
    return SeedReport(created=created, skipped_reasons=reasons)


def reset_user_data(session: Session, confirm: str, user_id: int | None = None) -> dict:
    """Dev-only destructive reset of USER DATA tables (spec §16.3).

    Requires the literal confirmation string 'RESET_USER_DATA'. Content tables
    are never touched here.
    """
    if confirm != "RESET_USER_DATA":
        raise ValueError("reset requires --confirm RESET_USER_DATA")
    from ..models import DailyUsage, Entitlement, Reading, ReadingCard, UserPreference

    deleted = {}
    q = session.query(User)
    if user_id is not None:
        q = q.filter(User.id == user_id)
    uids = [u.id for u in q.all()]
    if uids:
        rid_sub = session.query(Reading.id).filter(Reading.user_id.in_(uids)).subquery()
        deleted["reading_cards"] = session.query(ReadingCard).filter(
            ReadingCard.reading_id.in_(rid_sub)).delete(synchronize_session=False)
        deleted["readings"] = session.query(Reading).filter(Reading.user_id.in_(uids)).delete(synchronize_session=False)
        deleted["daily_usage"] = session.query(DailyUsage).filter(DailyUsage.user_id.in_(uids)).delete(synchronize_session=False)
        deleted["entitlements"] = session.query(Entitlement).filter(Entitlement.user_id.in_(uids)).delete(synchronize_session=False)
        deleted["payments"] = session.query(Payment).filter(Payment.user_id.in_(uids)).delete(synchronize_session=False)
        deleted["user_preferences"] = session.query(UserPreference).filter(UserPreference.user_id.in_(uids)).delete(synchronize_session=False)
        deleted["users"] = session.query(User).filter(User.id.in_(uids)).delete(synchronize_session=False)
    session.commit()
    return deleted
