"""Editorial advice content: tag rules, theme phrasing, position-role framing.

All blocks are pre-written editorial texts (deterministic, no runtime generation
by AI/LLM). The composer selects among them using the cards' tags, the reading
theme, and the interpretation role of the anchor card's position (spec §9.5).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Tag-based advice rules.
# Each rule: stable code, applicable tag codes, themes it applies to
# (None => any theme), priority (higher wins when several rules match).
# ---------------------------------------------------------------------------

TagAdviceRule = tuple[str, tuple[str, ...], tuple[str, ...] | None, int, str]

TAG_ADVICE_RULES: list[TagAdviceRule] = [
    # --- decision / hesitation ---
    ("hesitation_love", ("decision", "doubt"), ("love",), 40,
     "В близости откладывание решения тоже является решением. Выберите критерий, который для вас важнее сейчас, и честно назовите его вслух — партнёру или себе."),
    ("hesitation_work", ("decision", "doubt"), ("work",), 40,
     "Пока решение не принято, оно за вас уже принимают обстоятельства. Зафиксируйте два-три критерия выбора и выберите вариант, который не отменяет остальные двери."),
    ("hesitation_money", ("decision", "doubt"), ("money",), 40,
     "Сомнения в расходах и вложениях — сигнал не хватает данных. Выпишите сумму, срок и цель; если расчёт не складывается, это ответ «нет», а не повод ждать ещё."),
    ("hesitation_self_development", ("decision", "doubt"), ("self_development",), 40,
     "Сомнение часто маскирует страх ошибки. Разрешите себе пробный вариант с датой пересмотра: решить на две недели проще, чем решить навсегда."),
    ("hesitation", ("decision", "doubt"), None, 20,
     "Неопределённость — часть ситуации, а не препятствие к решению. Сформулируйте, какой новый факт способен изменить ваш выбор, и займитесь им."),
    ("avoid_choice", ("avoidance",), None, 30,
     "Карта указывает на уход от выбора. Верните вопрос в одну конкретную формулировку и дайте себе короткий срок на ответ — дольше откладывать означает выбирать чужой сценарий."),
    # --- conflict / boundaries / dialogue ---
    ("conflict_love", ("conflict", "betrayal", "rival"), ("love",), 42,
     "Тема конфликта в близости лечится не правотой, а договорённостью. Начните разговор с того, чего вы хотите для отношений, а не с перечня претензий."),
    ("conflict_work", ("conflict", "rival"), ("work",), 42,
     "В рабочем споре ценнее не победа, а сохранение дееспособности команды. Отделите позицию человека от его интересов и предложите один проверяемый компромисс."),
    ("conflict", ("conflict", "tension"), None, 28,
     "Конфликт показывает задетую ценность. Сначала признайте её для себя, затем обозначьте вслух — так у диалога появляется почва."),
    ("boundaries", ("boundaries",), None, 36,
     "Ситуация требует границы, а не переговоров. Спокойно назовите, что вы готовы делать, а что — нет, и держите эту рамку без оправданий."),
    ("defend", ("defend",), None, 30,
     "Есть смысл занять оборонительную позицию по одному фронту, но не по всем сразу. Выберите, что действительно нужно отстоять, и направьте туда основную силу."),
    # --- initiative / action ---
    ("initiative_work", ("start_action", "new_beginning"), ("work",), 42,
     "Импульс совпадает с рабочим контекстом: начните проект с первой видимой части — прототипа, письма, заявки. Полный план появится из движения, а не из ожидания."),
    ("initiative_money", ("start_action", "act_now"), ("money",), 42,
     "Для финансов важен первый практический шаг: заложить сумму, оформить вклад, сократить одну статью расходов. Маленькое действие сегодня стоит большого плана завтра."),
    ("initiative", ("start_action", "new_beginning"), None, 28,
     "Карта поддержки начала: сделайте первый шаг, пока мотивация свежая. Уменьшите масштаб задачи настолько, чтобы стало стыдно её не начать."),
    ("act_now", ("act_now",), None, 34,
     "Окно возможностей открыто сейчас. Определите минимальное необратимое действие и выполните его до конца дня; детали доделаете по ходу."),
    ("drive", ("drive", "momentum", "high_energy"), None, 30,
     "Энергия есть — используйте её направленнно: одна цель, один отрезок времени, без распыления. Разгон легко потерять о несколько дел сразу."),
    # --- waiting / observation / reflection ---
    ("wait_observe", ("observe", "mystery", "waiting_time"), None, 34,
     "Сейчас продуктивнее наблюдение, чем вмешательство. Договоритесь с собой о сроке паузы и о признаке, по которому поймёте, что пора действовать."),
    ("pause_rethink_self_development", ("pause", "reflection", "solitude"), ("self_development",), 44,
     "Это время тишины, а не упущенных возможностей. Выделите день наедине с собой и запишите три вопроса, ответы на которые вы от себя ждёте."),
    ("pause_rethink_work", ("pause", "rest"), ("work",), 44,
     "На работе пауза — часть результата: восстановление влияет на качество решений сильнее, чем ещё один аврал. Запланируйте отдых так же серьёзно, как дедлайн."),
    ("patience_harvest_money", ("waiting_time", "long_process", "patience_sp"), ("money",), 44,
     "Финансовый процесс созревает медленно: не пересаживайте росток. Проверьте график и позвольте плану работать без ваших ежедневных правок."),
    ("slow_down", ("slow_energy",), None, 26,
     "Темп ниже вашего привычного — это нормально для текущего этапа. Уберите половину задач из списка и доведите оставшееся до конца."),
    ("let_go", ("let_go", "ending", "departure"), None, 34,
     "Часть ситуации нужно отпустить, а не починить. Назовите конкретно, за что вы держитесь, и спросите, что освободится, если разжать руку."),
    # --- information / clarity ---
    ("seek_info", ("lack_of_information", "news", "hidden_problem"), None, 36,
     "Решения сейчас слепы: не хватает фактов. Составьте список вопросов и получите хотя бы один письменный ответ до следующего шага."),
    ("verify_illusion", ("illusion", "dreams"), None, 34,
     "Часть картины — ваши ожидания, а не реальность. Сверьте гипотезы с одним независимым источником и отделите «как я хочу» от «как есть»."),
    ("caution_risk", ("risk_event", "caution_type"), None, 34,
     "Риск допустим, но осознанный: заранее зафиксируйте цену худшего сценария и стоп-условие, при котором выходите из игры без сожалений."),
    # --- structure / discipline / planning ---
    ("structure", ("discipline", "responsibility", "plan", "strategy"), None, 34,
     "Ситуации нужна опора: правило, порядок или план. Соберите минимум — цель, следующий шаг, срок — и следуйте ему неделю без пересмотров."),
    ("routine_build", ("routine", "build", "continue"), None, 30,
     "Результат складывается из повторений. Выберите одно действие и держите его ежедневно; масштаб придёт позже, сначала — регулярность."),
    ("delegation", ("overwork", "burden"), None, 38,
     "Вы несёте больше, чем должно быть на одном человеке. Пересмотрите список обязательств и отдайте или отмените хотя бы один пункт."),
    ("ask_help", ("support", "mentor"), None, 32,
     "Это тот случай, где помощь ускоряет результат. Обратитесь к человеку с опытом именно в вашей задаче и задайте один конкретный вопрос."),
    # --- emotions / relationships ---
    ("talk_openly_rel_love", ("communication",), ("love",), 46,
     "В близости помогает прямой разговор без обвинений: скажите о своём чувстве и потребности одной фразой, дождитесь ответа и только потом продолжайте."),
    ("trust_step_love", ("trust", "partnership", "commitment"), ("love",), 40,
     "Доверие растёт через маленькие подтверждённые шаги. Договоритесь об одном обязательном действии друг для друга и выполните его раньше срока."),
    ("gratitude_practice", ("gratitude", "joy", "celebration"), None, 28,
     "Зафиксируйте то, что уже получилось: отметьте результат письменно и разделите его с тем, кто рядом. Это топливо для следующего этапа."),
    ("care_self_self_development", ("empathy", "sensitivity", "acceptance"), ("self_development",), 40,
     "Начните с принятия, а не с требований. Признайте текущее состояние без оценок и добавьте одну заботливую практику на этой неделе."),
    # --- resources / money ---
    ("budget_check_money", ("budget", "resources", "scarcity"), ("money",), 46,
     "Финансовая тревога лечится ясностью: поднимите реальные цифры доходов и расходов за месяц. Половина страхов исчезает на этапе подсчёта."),
    ("generosity_flow_money", ("generosity", "fair_exchange"), ("money",), 38,
     "Деньги любят движение в обе стороны: запланируйте посильную отдачу — помощь, подарок, оплату долга — это возвращает ощущение контроля."),
    ("secure_base", ("security", "savings", "stability_event"), None, 30,
     "Укрепите базу, прежде чем строить дальше: подушка, резерв по времени, запасной план. Устойчивость — тоже прогресс."),
    # --- growth / inner work ---
    ("one_practice_self_development", ("growth", "purpose", "awakening"), ("self_development",), 46,
     "Рост любит узкую дорожку: выберите одну практику и держите её две недели, записывая наблюдения. Ширину добавите после глубины."),
    ("study_step", ("learning", "curiosity"), None, 30,
     "Инвестиция в навык окупится на этом этапе. Возьмите один короткий курс или книгу и примените первый же урок на практике в течение недели."),
    ("balance_path", ("balance_sp", "adapt"), None, 30,
     "Жёсткость сейчас дороже гибкости. Найдите середину между «держать любой ценой» и «бросить»: скорректируйте интенсивность, не отменяя направление."),
    ("break_pattern", ("dependence", "attachment", "toxic_influence", "limiting_belief"), None, 46,
     "Карта про повторяющуюся схему. Прервите цикл самым коротким способом: измените одну деталь рутины или среды, которая запускает старое поведение."),
    ("fear_name", ("fear", "anxiety"), None, 38,
     "Страх уменьшается, когда назван. Опишите худший сценарий на бумаге и добавьте план действий на его случай — после этого можно двигаться."),
    ("rest_first", ("exhaustion", "low_energy"), None, 44,
     "Прежде чем решать что-либо важное, восстановите силы: сон, пауза, отказ от одной нагрузки. Решения на нуле энергии почти всегда ошибочны."),
    ("release_control", ("chaos", "crisis", "release"), None, 38,
     "Часть конструкции рушится — не удерживайте обломки. Держите только то, что действительно ваше: безопасность, обязательства перед людьми, ясные факты."),
    ("forgive_move", ("grief", "sadness"), None, 34,
     "Тяжёлое переживание нужно допрожить, а не закрасить: признайте потерю честно и не принимайте важных решений на пике эмоций."),
    ("intuition_listen", ("intuition",), None, 32,
     "Внутренний голос уже предлагает ответ, но вы ждёте внешних гарантий. Запишите первое, что приходит в голову о ситуации, и сверьтесь с этим списком через пару дней."),
]

# ---------------------------------------------------------------------------
# Theme-specific phrasing used by the synthesis fallback (level 4).
# Template receives the card's meaning text as {meaning}.
# ---------------------------------------------------------------------------

THEME_ADVICE_FRAMES: dict[str, str] = {
    "love": "В теме близости поступайте согласно этому смыслу: {meaning} Переведите его в один конкретный шаг по отношению к партнёру или к себе.",
    "work": "В рабочем контексте этот смысл переводится в действия: {meaning} Выберите задачу, результат которой заметят другие, и сделайте первый шаг.",
    "money": "В финансовых делах действуйте практично: {meaning} Оформите это как число, срок или правило — и проверьте на одном небольшом решении.",
    "self_development": "Для личного роста используйте этот смысл как практику: {meaning} Возьмите из него одно упражнение и держите его две недели.",
}

# Fallback frame when the theme is unknown (should not normally happen).
GENERIC_ADVICE_FRAME = "Опирайтесь на этот смысл: {meaning} Сведите его к одному действию, которое зависит только от вас."

# ---------------------------------------------------------------------------
# Position-role framing for the synthesis level.
# ---------------------------------------------------------------------------

POSITION_ROLE_FRAMES: dict[str, str] = {
    "advice": "",
    "challenge": "Главное препятствие снимается малым шагом: ",
    "resource": "Используйте доступный ресурс напрямую: ",
    "outcome": "Чтобы итог сложился благоприятно, поддержите его сейчас: ",
    "answer": "Ответ карты переводите в действие так: ",
    "general": "",
}


def _match_rule(rule: TagAdviceRule, tags: set[str], theme_code: str) -> bool:
    _code, tag_list, themes, _prio, _text = rule
    if not any(t in tags for t in tag_list):
        return False
    return themes is None or theme_code in themes


def select_tag_advice(tags: set[str], theme_code: str) -> tuple[str, str] | None:
    """Deterministically pick the best advice rule text for a card's tags+theme.

    Returns (rule_code, text) or None when no rule applies. When several rules
    match, the highest-priority one wins; ties are broken by the rule's stable
    position in the table, so the result never changes between runs.
    """
    best: tuple[int, int, str, str] | None = None  # (-priority, index, code, text)
    for idx, rule in enumerate(TAG_ADVICE_RULES):
        if not _match_rule(rule, tags, theme_code):
            continue
        code, _tags, _themes, prio, _text = rule
        key = (-prio, idx, code, "")
        if best is None or key < best:
            best = (-prio, idx, code, rule[4])
    if best is None:
        return None
    return best[2], best[3]


def rule_codes_for(tags: set[str], theme_code: str) -> list[str]:
    """All matching rule codes sorted deterministically (for tests/diagnostics)."""
    matched = [r for r in TAG_ADVICE_RULES if _match_rule(r, tags, theme_code)]
    matched.sort(key=lambda r: (-r[3], r[0]))
    return [r[0] for r in matched]
