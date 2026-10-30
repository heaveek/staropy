"""Bot handlers: /start, /help, /premium and the payment pipeline.

Payment security model (spec §13/§14):
  - only `successful_payment` inside a message from Telegram counts as proof;
  - `pre_checkout_query` is answered so the flow can complete but NEVER
    activates Premium;
  - verification of payload/amount/currency/user happens in the backend
    service layer against the DB (single source of truth); the bot only
    forwards fields taken from the authenticated Telegram update object;
  - retries are safe: backend confirm_payment is idempotent by
    external_payment_id; on transient backend errors we leave the message
    un-acked for re-delivery via getUpdates.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("bot.handlers")

WELCOME_TEXT = (
    "🔮 Таро-ассистент\n\n"
    "Расклады на колоде из 78 карт: карта дня, «да/нет», прошлое–настоящее–будущее, "
    "ситуация–совет–итог и подробный Кельтский крест.\n\n"
    "Один обычный расклад в день — бесплатно. Кельтский крест и полная история — с Premium.\n\n"
    "Нажмите кнопку ниже, чтобы открыть приложение."
)

HELP_TEXT = (
    "Как пользоваться:\n"
    "1. Откройте приложение кнопкой «Открыть таро».\n"
    "2. Выберите расклад и тему, задайте вопрос (необязательно).\n"
    "3. Получите трактовку; история доступна в приложении.\n\n"
    "Команды:\n"
    "/start — открыть приложение\n"
    "/help — эта справка\n"
    "/premium — статус и покупка Premium\n\n"
    "Расклады носят развлекательно-рефлексивный характер и не являются "
    "медицинским, юридическим или финансовым советом."
)


def build_start_keyboard(settings) -> list[list[dict]]:
    url = settings.mini_app_button_url
    rows = [[{"text": "🃏 Открыть таро", "url": url}]] if url else []
    return rows


def build_premium_keyboard(settings) -> list[list[dict]]:
    url = settings.mini_app_button_url
    rows = [[{"text": "💎 Открыть Premium", "url": url}]] if url else []
    return rows


async def handle_start(message, settings, reply) -> None:
    await reply(
        WELCOME_TEXT,
        reply_markup={"inline_keyboard": build_start_keyboard(settings)},
    )


async def handle_help(message, settings, reply) -> None:
    await reply(HELP_TEXT)


async def handle_premium_status(message, settings, status_client, reply) -> None:
    """Show REAL premium state from backend; never fabricate success."""
    try:
        data = await status_client.premium_status(int(message.from_user.id))
    except Exception as exc:  # noqa: BLE001 - report, don't fake
        logger.warning("premium status lookup failed: %s", type(exc).__name__)
        await reply("Не удалось получить статус Premium. Попробуйте позже.")
        return
    if data.get("is_premium"):
        until = data.get("active_until") or "бессрочно"
        await reply(f"💎 Premium активен до {until}.")
        return
    products = data.get("products") or []
    if not products:
        await reply(
            "Premium пока не настроен. Мы сообщим, когда покупка станет доступной."
        )
        return
    lines = ["Доступные тарифы Premium:"]
    for p in products:
        price = f"{p['price_amount']} ⭐" if p.get("currency") == "XTR" else f"{p['price_amount']} {p.get('currency', '')}"
        dur = f"{p['duration_days']} дн." if p.get("duration_days") else "разовый доступ"
        lines.append(f"• {p['name']} — {price} ({dur})")
    lines.append("Откройте приложение → вкладка Premium для покупки.")
    await reply(
        "\n".join(lines),
        reply_markup={"inline_keyboard": build_premium_keyboard(settings)},
    )


class PaymentBackendError(Exception):
    pass


class PaymentPermanentError(Exception):
    """Backend rejected the event definitively (4xx other than retryable)."""


async def process_successful_payment(
    *, telegram_id: int, external_payment_id: str, total_amount: int,
    currency: str, invoice_payload: str, confirm_fn, answer=None,
) -> dict:
    """Verify-and-confirm pipeline shared by aiogram handler and tests.

    confirm_fn: async callable(dict) -> dict with keys:
        ok (bool), optionally permanent (bool), status (str), error (str).
    Returns a result dict; raises PaymentBackendError on transient failures so
    the caller can leave the update un-acked and retry on redelivery.
    """
    if not external_payment_id:
        logger.error("payment event without telegram_payment_charge_id, rejecting")
        if answer:
            await answer("Платёж отклонён: нет идентификатора.", show_alert=True)
        raise PaymentPermanentError("missing_external_payment_id")

    event = {
        "telegram_id": telegram_id,
        "external_payment_id": external_payment_id,
        "total_amount": total_amount,
        "currency": currency,
        "invoice_payload": invoice_payload,
    }
    try:
        result = await confirm_fn(event)
    except Exception as exc:  # network/db hiccup => retryable
        logger.warning("confirm call failed (%s); will retry on redelivery", type(exc).__name__)
        raise PaymentBackendError(str(exc)) from exc

    if not result.get("ok"):
        if result.get("permanent"):
            logger.error("payment rejected permanently: %s", result.get("error"))
            if answer:
                await answer("Оплата не подтверждена. Обратитесь в поддержку.", show_alert=True)
            raise PaymentPermanentError(result.get("error", "rejected"))
        raise PaymentBackendError(result.get("error", "retryable"))

    status = result.get("status", "paid")
    if answer:
        await answer("Оплачено! ✨ Premium активирован.", show_alert=False)
    return {"status": status, "event": event}


async def process_pre_checkout_query(query) -> None:
    """Answer pre-checkout so Telegram can proceed. NOT proof of payment."""
    logger.info("pre_checkout received (payload=%s) — answering ok", getattr(query, "invoice_payload", "?"))
    await query.answer(ok=True)
