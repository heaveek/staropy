"""Unit tests for bot payment pipeline — no Telegram token required."""
from __future__ import annotations

import asyncio

import pytest

from bot.config import BotSettings, require_token
from bot.handlers import (
    PaymentBackendError, PaymentPermanentError, build_premium_keyboard,
    build_start_keyboard, handle_help, handle_premium_status, handle_start,
    process_pre_checkout_query, process_successful_payment,
)


def run(coro):
    return asyncio.run(coro)


class FakeAnswer:
    def __init__(self):
        self.calls = []
    async def __call__(self, text, show_alert=False):
        self.calls.append((text, show_alert))


EVENT = dict(telegram_id=111, external_payment_id="chg_1", total_amount=500,
             currency="XTR", invoice_payload="p1_u2_abc")


def make_confirm(result=None, exc=None, calls=None):
    async def fn(event):
        if calls is not None:
            calls.append(dict(event))
        if exc:
            raise exc
        return result or {"ok": True, "status": "paid"}
    return fn


def test_settings_from_env():
    s = BotSettings.from_env({"TELEGRAM_BOT_TOKEN": " 123:abc ", "BACKEND_BASE_URL": "http://x:1/"})
    assert s.telegram_bot_token == "123:abc"
    assert s.backend_base_url == "http://x:1"


def test_mini_app_button_url_deep_link():
    s = BotSettings(telegram_bot_username="tarot_bot", telegram_webapp_url="https://app.example/mini")
    url = s.mini_app_button_url
    assert url.startswith("tg://app?bot_username=tarot_bot")
    assert "https%3A%2F%2Fapp.example%2Fmini" in url


def test_require_token_raises_without_token():
    with pytest.raises(RuntimeError):
        require_token(BotSettings())
    require_token(BotSettings(telegram_bot_token="1:token"))  # no raise


def test_keyboards_empty_without_url():
    assert build_start_keyboard(BotSettings()) == []
    kb = build_start_keyboard(BotSettings(telegram_webapp_url="https://a.app"))
    assert kb[0][0]["url"] == "https://a.app"


def test_handle_start_and_help_reply_text():
    replies = []
    async def reply(text, **kw):
        replies.append((text, kw))
    run(handle_start(None, BotSettings(), reply))
    run(handle_help(None, BotSettings(), reply))
    assert "Таро-ассистент" in replies[0][0]
    assert replies[0][1]["reply_markup"]["inline_keyboard"] == []
    assert "/premium" in replies[1][0]


class FakeMessage:
    class _U: id = 111
    from_user = _U()


class FakeStatusClient:
    def __init__(self, data=None, exc=None):
        self.data, self.exc = data, exc
    async def premium_status(self, tid):
        if self.exc:
            raise self.exc
        return self.data


def test_premium_status_shows_products():
    replies = []
    async def reply(text, **kw): replies.append(text)
    client = FakeStatusClient({"products": [
        {"name": "Premium 30 дней", "price_amount": 149, "currency": "XTR", "duration_days": 30}]})
    run(handle_premium_status(FakeMessage(), BotSettings(), client, reply))
    assert "149 ⭐" in replies[0] and "30 дн." in replies[0]


def test_premium_status_not_configured_message():
    replies = []
    async def reply(text, **kw): replies.append(text)
    run(handle_premium_status(FakeMessage(), BotSettings(), FakeStatusClient({}), reply))
    assert "не настроен" in replies[0]


def test_premium_status_backend_error_no_fabrication():
    replies = []
    async def reply(text, **kw): replies.append(text)
    run(handle_premium_status(FakeMessage(), BotSettings(),
                              FakeStatusClient(exc=RuntimeError("down")), reply))
    assert "Не удалось" in replies[0]


def test_successful_payment_forwards_all_verified_fields():
    calls = []
    res = run(process_successful_payment(**EVENT, confirm_fn=make_confirm(calls=calls)))
    assert res["status"] == "paid"
    assert calls[0] == {k: v for k, v in EVENT.items()}


def test_missing_external_id_rejected_permanently():
    calls = []
    with pytest.raises(PaymentPermanentError):
        run(process_successful_payment(**{**EVENT, "external_payment_id": ""},
                                       confirm_fn=make_confirm(calls=calls), answer=FakeAnswer()))
    assert calls == []  # never forwarded


def test_transient_backend_failure_is_retryable():
    with pytest.raises(PaymentBackendError):
        run(process_successful_payment(**EVENT,
              confirm_fn=make_confirm({"ok": False, "permanent": False, "error": "network:x"})))


def test_confirm_exception_becomes_retryable():
    with pytest.raises(PaymentBackendError):
        run(process_successful_payment(**EVENT, confirm_fn=make_confirm(exc=OSError("net down"))))


def test_permanent_rejection_noted_to_user():
    ans = FakeAnswer()
    with pytest.raises(PaymentPermanentError):
        run(process_successful_payment(**EVENT,
              confirm_fn=make_confirm({"ok": False, "permanent": True, "error": "rejected:payment_amount_mismatch"}),
              answer=ans))
    assert "не подтверждена" in ans.calls[0][0]


def test_replay_same_event_ok_via_idempotent_backend():
    # Backend replay returns ok status paid again; no exception, single call each time
    calls = []
    fn = make_confirm({"ok": True, "status": "paid"}, calls=calls)
    run(process_successful_payment(**EVENT, confirm_fn=fn))
    run(process_successful_payment(**EVENT, confirm_fn=fn))
    assert len(calls) == 2  # forwarding twice is safe: idempotency enforced server-side


class FakePreCheckout:
    def __init__(self): self.answered = None; self.invoice_payload = "p1_u2_abc"
    async def answer(self, ok): self.answered = ok


def test_pre_checkout_answered_but_not_confirmation():
    q = FakePreCheckout()
    run(process_pre_checkout_query(q))
    assert q.answered is True
