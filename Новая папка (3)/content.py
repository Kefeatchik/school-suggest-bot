"""Извлечение контента из сообщения и его пересылка в чат/канал."""
from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo, Message


def extract_content(message: Message) -> tuple[str, str | None, Any] | None:
    """Вернуть (content_type, текст/подпись, media) для одиночного сообщения."""
    if message.text:
        return "text", message.text, None
    if message.photo:
        return "photo", message.caption, {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return "video", message.caption, {"type": "video", "file_id": message.video.file_id}
    if message.animation:
        return "animation", message.caption, {"type": "animation", "file_id": message.animation.file_id}
    if message.voice:
        return "voice", message.caption, {"type": "voice", "file_id": message.voice.file_id}
    if message.video_note:
        return "video_note", message.caption, {"type": "video_note", "file_id": message.video_note.file_id}
    if message.document:
        return "document", message.caption, {"type": "document", "file_id": message.document.file_id}
    if message.sticker:
        return "sticker", None, {"type": "sticker", "file_id": message.sticker.file_id}
    return None


async def send_content(
    bot: Bot,
    chat_id: int,
    content_type: str,
    text: str | None,
    media: Any,
    reply_markup: Any = None,
):
    """Отправить сохранённый пост в чат. Контент шлётся как есть (без HTML-парсинга)."""
    if content_type == "text":
        return await bot.send_message(chat_id, text, reply_markup=reply_markup)
    if content_type == "photo":
        return await bot.send_photo(
            chat_id, media["file_id"], caption=text or None, reply_markup=reply_markup
        )
    if content_type == "video":
        return await bot.send_video(
            chat_id, media["file_id"], caption=text or None, reply_markup=reply_markup
        )
    if content_type == "animation":
        return await bot.send_animation(
            chat_id, media["file_id"], caption=text or None, reply_markup=reply_markup
        )
    if content_type == "document":
        return await bot.send_document(
            chat_id, media["file_id"], caption=text or None, reply_markup=reply_markup
        )
    if content_type == "voice":
        return await bot.send_voice(chat_id, media["file_id"], reply_markup=reply_markup)
    if content_type == "video_note":
        return await bot.send_video_note(chat_id, media["file_id"], reply_markup=reply_markup)
    if content_type == "sticker":
        return await bot.send_sticker(chat_id, media["file_id"], reply_markup=reply_markup)
    if content_type == "media_group":
        return await _send_media_group(bot, chat_id, media, text)
    raise ValueError(f"Неизвестный тип контента: {content_type}")


async def _send_media_group(
    bot: Bot, chat_id: int, media: list[dict], caption: str | None
):
    items: list[Any] = []
    for i, item in enumerate(media):
        cap = caption if i == 0 else None
        if item["type"] == "photo":
            items.append(InputMediaPhoto(media=item["file_id"], caption=cap))
        else:
            items.append(InputMediaVideo(media=item["file_id"], caption=cap))
    return await bot.send_media_group(chat_id, media=items)
