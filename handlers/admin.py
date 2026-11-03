"""Обработчики админов: модерация, бан/мут, статистика."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import context
from content import send_content
from keyboards import mute_menu, profile_keyboard

logger = logging.getLogger(__name__)

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in context.cfg.admin_ids


def _fmt_user(row) -> str:
    first = escape(row["first_name"] or "")
    last = escape(row["last_name"] or "")
    name = (first + " " + last).strip() or "—"
    username = f"@{escape(row['username'])}" if row["username"] else "нет"
    return (
        f"👤 <b>{name}</b>\n"
        f"🆔 ID: <code>{row['user_id']}</code>\n"
        f"📛 Username: {username}"
    )


# ---------- модерация постов ----------
@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    await _review(cb, post_id, "approved")


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    await _review(cb, post_id, "rejected")


async def _review(cb: CallbackQuery, post_id: int, status: str) -> None:
    post = await context.db.get_post(post_id)
    if post is None:
        await cb.answer("Пост не найден.", show_alert=True)
        return
    if post["status"] != "pending":
        await cb.answer("Этот пост уже обработан.", show_alert=True)
        return

    await context.db.set_post_status(post_id, status)

    if status == "approved":
        await _publish(post, cb.bot)
        suffix = "✅ Одобрено и опубликовано"
        await _notify(cb.bot, post["user_id"], "✅ Твой пост одобрен и опубликован в канале!")
    else:
        suffix = "❌ Отклонено"
        await _notify(cb.bot, post["user_id"], "❌ Твой пост отклонён модератором.")

    await _mark_reviewed(cb, suffix)
    await cb.answer()


async def _publish(post, bot: Bot) -> None:
    if not context.cfg.channel_id:
        return
    media = json.loads(post["media_json"]) if post["media_json"] else None
    try:
        await send_content(
            bot, context.cfg.channel_id, post["content_type"], post["text"], media
        )
    except Exception:
        logger.exception("Ошибка публикации поста #%s в канал", post["post_id"])


async def _notify(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass


async def _mark_reviewed(cb: CallbackQuery, suffix: str) -> None:
    msg = cb.message
    try:
        if msg.text is not None:
            await msg.edit_text(f"{msg.text}\n\n{suffix}", reply_markup=None)
            return
    except Exception:
        pass
    try:
        if msg.caption is not None:
            await msg.edit_caption(caption=f"{msg.caption}\n\n{suffix}", reply_markup=None)
            return
    except Exception:
        pass
    try:
        await msg.answer(suffix)
    except Exception:
        pass


# ---------- профиль отправителя ----------
@router.callback_query(F.data.startswith("profile:"))
async def cb_profile(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    user_id = int(cb.data.split(":", 1)[1])
    await _show_profile(cb, user_id)


async def _show_profile(cb: CallbackQuery, user_id: int) -> None:
    row = await context.db.get_user(user_id)
    if row is None:
        await cb.answer("Пользователь не найден.", show_alert=True)
        return

    stats = await context.db.user_post_stats(user_id)
    now = int(time.time())

    if row["banned"]:
        status = "⛔️ Забанен"
    elif row["mute_until"] > now:
        until = datetime.fromtimestamp(row["mute_until"]).strftime("%d.%m.%Y %H:%M")
        status = f"🔇 В муте до {until}"
    else:
        status = "🟢 Активен"

    text = (
        "<b>Профиль отправителя</b>\n\n"
        f"{_fmt_user(row)}\n"
        f"📅 В боте с: {datetime.fromtimestamp(row['created_at']).strftime('%d.%m.%Y')}\n\n"
        f"📊 Постов всего: {stats['total']}\n"
        f"⏳ На модерации: {stats['pending']}\n"
        f"✅ Одобрено: {stats['approved']}\n"
        f"❌ Отклонено: {stats['rejected']}\n\n"
        f"Статус: {status}"
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=profile_keyboard(user_id, bool(row["banned"])))
    await cb.answer()


# ---------- бан / мут ----------
@router.callback_query(F.data.startswith("ban:"))
async def cb_ban(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    user_id = int(cb.data.split(":", 1)[1])
    await context.db.set_ban(user_id, True)
    await cb.message.answer(f"⛔️ Пользователь <code>{user_id}</code> забанен.", parse_mode="HTML")
    await cb.answer("Пользователь забанен", show_alert=True)


@router.callback_query(F.data.startswith("unban:"))
async def cb_unban(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    user_id = int(cb.data.split(":", 1)[1])
    await context.db.set_ban(user_id, False)
    await cb.message.answer(f"✅ Пользователь <code>{user_id}</code> разбанен.", parse_mode="HTML")
    await cb.answer("Пользователь разбанен", show_alert=True)


@router.callback_query(F.data.startswith("mute:"))
async def cb_mute(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    user_id = int(cb.data.split(":", 1)[1])
    await cb.message.answer("Выбери срок мута:", reply_markup=mute_menu(user_id))
    await cb.answer()


@router.callback_query(F.data.startswith("mute_set:"))
async def cb_mute_set(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    _, user_id, seconds = cb.data.split(":")
    user_id = int(user_id)
    seconds = int(seconds)
    until = int(time.time()) + seconds
    await context.db.set_mute(user_id, until)
    until_str = datetime.fromtimestamp(until).strftime("%d.%m.%Y %H:%M")
    await cb.message.answer(f"🔇 Пользователь <code>{user_id}</code> в муте до {until_str}.", parse_mode="HTML")
    await cb.answer("Мут выдан", show_alert=True)


@router.callback_query(F.data == "hide")
async def cb_hide(cb: CallbackQuery) -> None:
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()


# ---------- команды ----------
@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Эта команда только для админов.")
        return
    s = await context.db.stats()
    text = (
        "<b>📊 Статистика</b>\n\n"
        f"👥 Пользователей: {s['users']}\n"
        f"📝 Постов всего: {s['posts']}\n"
        f"⏳ На модерации: {s['pending']}\n"
        f"✅ Одобрено: {s['approved']}\n"
        f"❌ Отклонено: {s['rejected']}\n"
        f"⛔️ Забанено: {s['banned']}\n"
        f"🔇 В муте: {s['muted']}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(
        f"💬 Chat ID: <code>{message.chat.id}</code>\n"
        f"👤 Твой ID: <code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


def _target_id(message: Message) -> int | None:
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    parts = message.text.split()
    if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
        return int(parts[1])
    return None


@router.message(Command("ban"))
async def cmd_ban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Эта команда только для админов.")
        return
    user_id = _target_id(message)
    if user_id is None:
        await message.answer("Использование: /ban <user_id> или ответь на сообщение пользователя.")
        return
    await context.db.set_ban(user_id, True)
    await message.answer(f"⛔️ Пользователь <code>{user_id}</code> забанен.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Эта команда только для админов.")
        return
    user_id = _target_id(message)
    if user_id is None:
        await message.answer("Использование: /unban <user_id> или ответь на сообщение пользователя.")
        return
    await context.db.set_ban(user_id, False)
    await message.answer(f"✅ Пользователь <code>{user_id}</code> разбанен.", parse_mode="HTML")


@router.message(Command("mute"))
async def cmd_mute(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Эта команда только для админов.")
        return
    parts = message.text.split()
    user_id: int | None = None
    minutes: int | None = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        if len(parts) >= 2 and parts[1].isdigit():
            minutes = int(parts[1])
    else:
        if len(parts) >= 3 and parts[1].lstrip("-").isdigit() and parts[2].isdigit():
            user_id = int(parts[1])
            minutes = int(parts[2])

    if user_id is None or minutes is None:
        await message.answer(
            "Использование: /mute <user_id> <минуты> или ответь на сообщение: /mute <минуты>"
        )
        return

    until = int(time.time()) + minutes * 60
    await context.db.set_mute(user_id, until)
    await message.answer(
        f"🔇 Пользователь <code>{user_id}</code> в муте на {minutes} мин.", parse_mode="HTML"
    )
