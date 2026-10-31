"""Advice block tests: context-dependence, determinism, no universal stub.

Covers spec requirements §9.5 (deterministic composer) and the advice fix:
advice must depend on cards, tags, theme and position role — not be one
repeated phrase for every reading.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Card, Spread, Theme
from app.services.composer import (
    UNIVERSAL_ADVICE_TEXT,
    PositionResult,
    compose_advice,
    compose_reading,
)
from app.tarot_content.advice import TAG_ADVICE_RULES, rule_codes_for, select_tag_advice

SPREADS_ALL = ["daily_card", "yes_no", "past_present_future", "situation_advice_outcome", "celtic_cross"]
FREE_SPREADS = ["daily_card", "yes_no", "past_present_future", "situation_advice_outcome"]
THEMES = ["love", "work", "money", "self_development"]


def _session():
    from app.db.session import get_session_factory
    return get_session_factory()()


# ---------------------------------------------------------------------------
# Pure content-table tests (no DB needed)
# ---------------------------------------------------------------------------

def test_rule_table_is_valid_and_deterministic():
    codes = [r[0] for r in TAG_ADVICE_RULES]
    assert len(set(codes)) == len(codes), "rule codes must be unique"
    for code, tags, themes, prio, text in TAG_ADVICE_RULES:
        assert tags and all(t.strip() for t in tags)
        assert text and len(text) > 40
        if themes is not None:
            assert set(themes) <= set(THEMES)
    # same input -> same pick, repeated many times
    key_tags = {"decision", "doubt"}
    picks = {select_tag_advice(key_tags, "love")[1] for _ in range(50)}
    assert len(picks) == 1


def test_different_semantic_tags_give_different_advice():
    hesitation = select_tag_advice({"decision", "doubt"}, "work")
    initiative = select_tag_advice({"start_action", "act_now"}, "work")
    waiting = select_tag_advice({"wait", "observe"}, "work")
    conflict = select_tag_advice({"conflict", "tension"}, "work")
    assert hesitation and initiative and waiting and conflict
    texts = {hesitation[1], initiative[1], waiting[1], conflict[1]}
    assert len(texts) == 4, "distinct semantics must map to distinct advice"
    # waiting card must NOT push immediate action
    assert "немедленно действ" not in waiting[1].lower()
    # conflict advice mentions dialogue/boundary/compromise semantics
    assert any(w in conflict[1].lower() for w in ("разговор", "диалог", "компромисс", "границ"))


def test_theme_changes_advice_when_rules_are_themed():
    tags = {"decision", "doubt"}
    love = select_tag_advice(tags, "love")[1]
    money = select_tag_advice(tags, "money")[1]
    dev = select_tag_advice(tags, "self_development")[1]
    assert len({love, money, dev}) == 3
    assert "близост" in love.lower() or "партнёр" in love.lower()
    assert "расход" in money.lower() or "вложен" in money.lower() or "сумм" in money.lower()
    assert "практик" in dev.lower() or "пробный вариант" in dev.lower()


def test_unknown_tags_return_none_for_rule_level():
    assert select_tag_advice({"nonexistent_tag_xyz"}, "love") is None
    assert rule_codes_for({"nonexistent_tag_xyz"}, "love") == []


# ---------------------------------------------------------------------------
# DB-backed composer cascade tests
# ---------------------------------------------------------------------------

def _pr(card_id: int, card_code: str, name: str, rendered: str, role: str, source: str = "universal") -> PositionResult:
    return PositionResult(
        position_number=1, position_id=1, position_code="p", position_name=name,
        card_id=card_id, card_code=card_code, card_name_ru=name, orientation="upright",
        meaning_source=source, selected_meaning_id=None, rendered_text=rendered,
        interpretation_role=role,
    )


@pytest.fixture()
def seeded_db(seed):
    """Ensure content is loaded; yield a session."""
    session = _session()
    try:
        yield session
    finally:
        session.close()


def _card(session, code):
    return session.scalar(select(Card).where(Card.code == code))


def _theme(session, code):
    return session.scalar(select(Theme).where(Theme.code == code))


def _spread(session, code):
    return session.scalar(select(Spread).where(Spread.code == code))


def test_anchor_prefers_advice_role_position(seeded_db):
    fool = _card(seeded_db, "major_00_fool")
    lovers = _card(seeded_db, "major_06_lovers")
    results = [
        _pr(fool.id, fool.code, fool.name_ru, "Начало без гарантий.", "general"),
        _pr(lovers.id, lovers.code, lovers.name_ru, "Честный выбор ценностей.", "advice"),
    ]
    advice = compose_advice(seeded_db, results, "love", 1, _theme(seeded_db, "love").id)
    # anchor should be the lovers/advice-role card => decision/partnership themed rules
    assert advice != UNIVERSAL_ADVICE_TEXT
    assert "решен" in advice.lower() or "довер" in advice.lower() or "выбор" in advice.lower()


def test_per_card_db_template_beats_tag_rules(seeded_db):
    card = _card(seeded_db, "major_00_fool")
    from app.models import InterpretationTemplate
    tpl = InterpretationTemplate(
        template_type="advice", spread_id=None, theme_id=None,
        position_code="advice:major_00_fool:money",
        template_text="ТЕСТОВЫЙ-ШАБЛОН: в деньгах начните с малого пробного шага.",
        priority=50, is_active=True, review_status="approved",
    )
    seeded_db.add(tpl)
    seeded_db.commit()
    try:
        results = [_pr(card.id, card.code, card.name_ru, "Начало без гарантий.", "advice")]
        advice = compose_advice(seeded_db, results, "money", 1, _theme(seeded_db, "money").id)
        assert advice.startswith("ТЕСТОВЫЙ-ШАБЛОН")
        # other theme does not see the money-specific template
        advice2 = compose_advice(seeded_db, results, "love", 1, _theme(seeded_db, "love").id)
        assert not advice2.startswith("ТЕСТОВЫЙ-ШАБЛОН")
    finally:
        seeded_db.delete(tpl)
        seeded_db.commit()


def test_fallback_synthesizes_from_meaning_not_stub(seeded_db):
    """Card with no tag rules and no templates -> synthesized from its meaning."""
    # swords_page has skepticism/news tags; news triggers seek_info rule, so use
    # a synthetic unknown card id with empty tags to force synthesis level.
    results = [_pr(999999, "synthetic_card", "Синтетическая карта",
                   "Текст значения этой карты о наблюдении.", "advice")]
    advice = compose_advice(seeded_db, results, "work", 1, _theme(seeded_db, "work").id)
    assert advice != UNIVERSAL_ADVICE_TEXT
    assert "рабочем контексте" in advice.lower()
    assert "наблюдении" in advice.lower(), "synthesis must reuse the card's meaning"


def test_fallback_with_meaning_fallback_source_still_not_universal(seeded_db):
    results = [_pr(999998, "synthetic_card2", "Ещё одна карта",
                   "Заглушка про подготовку текста.", "outcome", source="fallback")]
    advice = compose_advice(seeded_db, results, "love", 1, _theme(seeded_db, "love").id)
    assert advice != UNIVERSAL_ADVICE_TEXT
    assert len(advice) > 30


def test_position_role_influences_synthesis(seeded_db):
    rendered = "Пауза и внимание к тому, что ещё не сказано."
    a1 = compose_advice(seeded_db, [_pr(999997, "x1", "X", rendered, "resource")],
                        "self_development", 1, _theme(seeded_db, "self_development").id)
    a2 = compose_advice(seeded_db, [_pr(999996, "x2", "X", rendered, "outcome")],
                        "self_development", 1, _theme(seeded_db, "self_development").id)
    assert a1 != a2
    assert "ресурс" in a1.lower()
    assert "итог" in a2.lower()


# ---------------------------------------------------------------------------
# End-to-end API tests over all five spreads
# ---------------------------------------------------------------------------

def _create(client, headers, spread, theme, key):
    r = client.post("/api/v1/readings", headers=headers, json={
        "spread_code": spread, "theme_code": theme, "question": None,
        "idempotency_key": key,
    })
    assert r.status_code == 200, r.text
    rid = r.json()["reading_id"]
    d = client.get(f"/api/v1/readings/{rid}", headers=headers)
    assert d.status_code == 200
    return d.json()


def test_api_advice_varies_between_readings(client, seed, fresh_tg_id):
    from tests.conftest import user_headers
    h = user_headers(fresh_tg_id)
    advices = []
    for i, (spread, theme) in enumerate(zip(FREE_SPREADS + ["daily_card"], THEMES)):
        body = _create(client, h, spread, theme, f"adv-{i}")
        advice = body["advice"]
        assert advice, "advice must never be empty"
        assert advice != UNIVERSAL_ADVICE_TEXT, "universal stub must not be served"
        advices.append(advice)
    # at least most of them differ across different spreads/themes
    assert len(set(advices)) >= 4, f"expected varied advice, got: {advices}"


def test_api_advice_deterministic_on_replay(client, seed, fresh_tg_id):
    from tests.conftest import user_headers
    h = user_headers(fresh_tg_id)
    first = _create(client, h, "situation_advice_outcome", "work", "det-1")
    replay = client.post("/api/v1/readings", headers=h, json={
        "spread_code": "situation_advice_outcome", "theme_code": "work",
        "question": None, "idempotency_key": "det-1",
    }).json()
    second = client.get(f"/api/v1/readings/{replay['reading_id']}", headers=h).json()
    assert first["advice"] == second["advice"]
    assert first["snapshot"]["advice"] == second["snapshot"]["advice"]


def test_legacy_universal_template_never_served(client, seed, fresh_tg_id):
    """The old generic row still exists in DB (compatibility) but must not reach users."""
    from tests.conftest import user_headers
    h = user_headers(fresh_tg_id)
    for spread in FREE_SPREADS:
        body = _create(client, h, spread, "self_development", f"legacy-{spread}")
        assert body["advice"] != UNIVERSAL_ADVICE_TEXT
