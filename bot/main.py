"""Telegram bot entrypoint (aiogram 3.x).

Run:  python -m bot.main   (from repo root, with env vars set)
Requires TELEGRAM_BOT_TOKEN; refuses to start without it (no silent fallbacks).
"""
from __future__ import annotations

import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .backend_client import BackendClient
from .config import BotSettings, require_token
from .handlers import (
    HELP_TEXT, WELCOME_TEXT, PaymentBackendError, PaymentPermanentError,
    process_pre_checkout_query, process_successful_payment,
)

logger = logging.getLogger("bot")


def _kb(url: str, text: str) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])


def build_dispatcher(settings: BotSettings, backend: BackendClient) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message: Message, bot: Bot) -> None:
        await bot.send_message(message.chat.id, WELCOME_TEXT,
                               reply_markup=_kb(settings.mini_app_button_url, "🃏 Открыть таро"))

    @dp.message(Command("help"))
    async def cmd_help(message: Message, bot: Bot) -> None:
        await bot.send_message(message.chat.id, HELP_TEXT)

    @dp.message(Command("premium"))
    async def cmd_premium(message: Message, bot: Bot) -> None:
        try:
            data = await backend.premium_status(int(message.from_user.id))
        except Exception:  # noqa: BLE001
            logger.exception("premium status failed")
            await bot.send_message(message.chat.id,
                                   "Не удалось получить статус Premium. Попробуйте позже.")
            return
        products = data.get("products") or []
        if not products:
            await bot.send_message(message.chat.id,
                                   "Premium пока не настроен. Мы сообщим, когда покупка станет доступной.")
            return
        lines = ["Доступные тарифы Premium:"]
        for p in products:
            price = f"{p['price_amount']} ⭐" if p.get("currency") == "XTR" else \
                f"{p['price_amount']} {p.get('currency', '')}"
            dur = f"{p['duration_days']} дн." if p.get("duration_days") else "разовый доступ"
            lines.append(f"• {p['name']} — {price} ({dur})")
        lines.append("Откройте приложение → вкладка Premium для покупки.")
        await bot.send_message(message.chat.id, "\n".join(lines),
                               reply_markup=_kb(settings.mini_app_button_url, "💎 Открыть Premium"))

    @dp.pre_checkout_query()
    async def on_pre_checkout(pre_checkout_query, bot: Bot) -> None:
        # Answering pre-checkout is NOT a payment confirmation (spec §14).
        await process_pre_checkout_query(pre_checkout_query)

    @dp.message(F.successful_payment)
    async def on_successful_payment(message: Message, bot: Bot) -> None:
        sp = message.successful_payment
        user_id = int(message.from_user.id) if message.from_user else 0
        try:
            await process_successful_payment(
                telegram_id=user_id,
                external_payment_id=sp.telegram_payment_charge_id,
                total_amount=sp.total_amount,
                currency=sp.currency,
                invoice_payload=sp.invoice_payload,
                confirm_fn=backend.confirm_payment_event,
            )
            await bot.send_message(message.chat.id,
                                   "Оплата подтверждена ✨ Premium активирован. "
                                   "Вернитесь в приложение — статус обновится при следующем открытии.")
        except PaymentPermanentError:
            await bot.send_message(message.chat.id,
                                   "Оплата не подтверждена системой. Обратитесь в поддержку.")
        except PaymentBackendError:
            # Transient backend failure: do NOT claim success; Telegram will
            # re-deliver the update after our next polling cycle. Notify softly.
            await bot.send_message(message.chat.id,
                                   "Получили оплату, но подтверждение задерживается. "
                                   "Попробуйте открыть приложение через минуту; если не появится — напишите в поддержку.")

    return dp


async def run_polling(settings: BotSettings) -> None:
    require_token(settings)
    backend = BackendClient(settings)
    bot = Bot(token=settings.telegram_bot_token,
              default=DefaultBotProperties(parse_mode=None))
    dp = build_dispatcher(settings, backend)
    try:
        me = await bot.get_me()
        logger.info("bot started as @%s", me.username)
        await dp.start_polling(bot)
    finally:
        await backend.aclose()
        await bot.session.close()


def main() -> None:
    settings = BotSettings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        import asyncio
        asyncio.run(run_polling(settings))
    except RuntimeError as exc:
        logger.critical("%s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
