"""Точка входа: школьная анонимная «предложка».

Режимы:
- WEBHOOK_URL / RENDER_EXTERNAL_URL заданы → webhook-режим (для Render и т.п.).
- иначе → long-polling (локальный запуск).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Безопасный вывод в консоль: не падать из-за кодировки кириллицы в cmd.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

from aiogram import Bot, Dispatcher

import context
from config import Config
from database import Database
from handlers import admin, user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

WEBHOOK_PATH = "/webhook"


def _build_bot(cfg: Config) -> Bot:
    session = None
    if cfg.proxy_url:
        from aiohttp import ClientSession
        from aiohttp_socks import ProxyConnector

        session = ClientSession(connector=ProxyConnector.from_url(cfg.proxy_url))
    return Bot(token=cfg.bot_token, session=session)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # admin-роутер первым, чтобы команды (/stats, /ban, /mute …) не перехватывались
    # catch-all обработчиком пользовательского роутера.
    dp.include_router(admin.router)
    dp.include_router(user.router)
    return dp


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    """Webhook-режим: aiohttp-сервер + /health для Render."""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    base_url = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("WEBHOOK_URL/RENDER_EXTERNAL_URL не задан")
    secret = os.getenv("WEBHOOK_SECRET", "") or None
    port = int(os.getenv("PORT", "8080"))
    webhook_url = f"{base_url}{WEBHOOK_PATH}"

    async def _set_webhook(bot: Bot) -> None:
        try:
            await bot.set_webhook(webhook_url, secret_token=secret)
            logging.info("Webhook установлен: %s", webhook_url)
        except Exception:
            logging.exception("Не удалось установить webhook")

    async def on_startup(bot: Bot) -> None:
        # Не блокируем старт HTTP-сервера ожиданием Telegram:
        # webhook ставим в фоне, чтобы /health отвечал сразу.
        asyncio.create_task(_set_webhook(bot))

    dp.startup.register(on_startup)

    async def health(_request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(
        app, path=WEBHOOK_PATH
    )
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Webhook-сервер слушает порт %s", port)
    await asyncio.Event().wait()


async def main() -> None:
    cfg = Config.from_env()
    db = Database()
    await db.connect()
    context.init(db, cfg)

    bot = _build_bot(cfg)
    dp = _build_dispatcher()

    me = await bot.get_me()
    logging.info("Бот запущен: @%s (id=%s)", me.username, me.id)

    if not cfg.admin_ids:
        logging.warning("ADMIN_IDS не задан — модерация не будет работать.")
    if not cfg.channel_id:
        logging.warning("CHANNEL_ID не задан — одобренные посты не будут публиковаться.")
    if not cfg.moderation_chat_id:
        logging.warning("MODERATION_CHAT_ID не задан — посты не будут попадать на модерацию.")

    base_url = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL")

    try:
        if base_url:
            await _run_webhook(bot, dp)
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
    finally:
        await db.close()
        try:
            await bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановлено.")
