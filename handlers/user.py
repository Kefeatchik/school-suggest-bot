"""Обработчики пользователей: приём постов в предложку."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import context
from content import extract_content, send_content
from keyboards import moderation_keyboard

logger = logging.getLogger(__name__)

router = Router(name="user")

# Сборка медиагрупп (альбомов из нескольких фото/видео)
MEDIA_GROUPS: dict[str, list[Message]] = {}
FLUSH_TASKS: dict[str, asyncio.Task] = {}

WELCOME = (
    "Привет! 👋 Это анонимная «предложка» нашей подслушки.\n\n"
    "Просто отправь сюда своё сообщение — текст, фото, видео, голосовое или кружок. "
    "Оно попадёт на модерацию, и если всё ок, будет опубликовано в канале "
    "<b>полностью анонимно</b> — твой ник никто не увидит.\n\n"
    "📌 Команды:\n"
    "/start — главное\n"
    "/help — правила и помощь"
)

HELP = (
    "📖 Как это работает\n"
    "1️⃣ Ты отправляешь боту сообщение.\n"
    "2️⃣ Оно уходит на модерацию админам.\n"
    "3️⃣ Если всё ок — публикуется анонимно в канал.\n\n"
    "🙅‍♂️ Запрещено: оскорбления, травля, реклама, личные данные других людей, угрозы. "
    "За нарушения — мут или бан.\n\n"
    "Если твой пост не опубликовали — значит, он не прошёл модерацию."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    await context.db.get_or_create_user(
        user.id, user.username, user.first_name, user.last_name
    )
    await message.answer(WELCOME, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, parse_mode="HTML")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, bot: Bot) -> None:
    await _process_single(bot, message)


@router.message(
    F.content_type.in_(
        {ContentType.PHOTO, ContentType.VIDEO, ContentType.ANIMATION, ContentType.DOCUMENT}
    )
)
async def handle_media(message: Message, bot: Bot) -> None:
    if message.media_group_id:
        await _collect_group(bot, message)
    else:
        await _process_single(bot, message)


@router.message(
    F.content_type.in_({ContentType.VOICE, ContentType.VIDEO_NOTE, ContentType.STICKER})
)
async def handle_other_media(message: Message, bot: Bot) -> None:
    await _process_single(bot, message)


@router.message()
async def handle_unsupported(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Неизвестная команда. Попробуй /help.")
        return
    await message.answer(
        "⚠️ Этот тип сообщений не поддерживается. "
        "Отправь текст, фото, видео, голосовое или кружок."
    )


async def _process_single(bot: Bot, message: Message) -> None:
    content = extract_content(message)
    if content is None:
        await bot.send_message(message.chat.id, "⚠️ Не удалось распознать сообщение.")
        return
    content_type, text, media = content
    await _submit(bot, message, content_type, text, media)


async def _submit(
    bot: Bot, message: Message, content_type: str, text: str | None, media
) -> None:
    user = message.from_user
    await context.db.get_or_create_user(
        user.id, user.username, user.first_name, user.last_name
    )

    if await context.db.is_banned(user.id):
        await bot.send_message(message.chat.id, "⛔️ Ты заблокирован и не можешь отправлять посты.")
        return

    mute_until = await context.db.mute_until(user.id)
    now = int(time.time())
    if mute_until > now:
        until = datetime.fromtimestamp(mute_until).strftime("%d.%m.%Y в %H:%M")
        await bot.send_message(message.chat.id, f"🔇 Ты в муте до {until}. Немного подожди.")
        return

    media_json = json.dumps(media, ensure_ascii=False) if media is not None else None
    post_id = await context.db.create_post(user.id, content_type, text, media_json)

    await bot.send_message(message.chat.id, "✅ Получено! Твой пост ушёл на модерацию.")
    await _send_to_moderation(bot, post_id)


async def _send_to_moderation(bot: Bot, post_id: int) -> None:
    if not context.cfg.moderation_chat_id:
        return
    post = await context.db.get_post(post_id)
    if post is None:
        return

    kb = moderation_keyboard(post["post_id"], post["user_id"])
    media = json.loads(post["media_json"]) if post["media_json"] else None

    try:
        if post["content_type"] == "media_group":
            await send_content(
                bot, context.cfg.moderation_chat_id, "media_group", post["text"], media
            )
            await bot.send_message(
                context.cfg.moderation_chat_id,
                f"📥 Пост #{post['post_id']} (анонимно) — на модерации",
                reply_markup=kb,
            )
        else:
            await send_content(
                bot,
                context.cfg.moderation_chat_id,
                post["content_type"],
                post["text"],
                media,
                reply_markup=kb,
            )
    except Exception:
        logger.exception("Не удалось отправить пост #%s на модерацию", post_id)


async def _collect_group(bot: Bot, message: Message) -> None:
    key = f"{message.from_user.id}:{message.media_group_id}"
    MEDIA_GROUPS.setdefault(key, []).append(message)

    task = FLUSH_TASKS.get(key)
    if task and not task.done():
        task.cancel()
    FLUSH_TASKS[key] = asyncio.create_task(_flush_group(key, bot))


async def _flush_group(key: str, bot: Bot) -> None:
    try:
        await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        return

    messages = MEDIA_GROUPS.pop(key, None)
    FLUSH_TASKS.pop(key, None)
    if not messages:
        return

    messages.sort(key=lambda m: m.message_id)
    media: list[dict] = []
    caption: str | None = None
    for m in messages:
        if m.photo:
            media.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            media.append({"type": "video", "file_id": m.video.file_id})
        elif m.animation:
            media.append({"type": "video", "file_id": m.animation.file_id})
        elif m.document:
            media.append({"type": "document", "file_id": m.document.file_id})
        if m.caption:
            caption = m.caption

    if not media:
        return

    try:
        await _submit(bot, messages[0], "media_group", caption, media)
    except Exception:
        logger.exception("Ошибка обработки медиагруппы")
