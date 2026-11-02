"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def moderation_keyboard(post_id: int, user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Одобрить", callback_data=f"approve:{post_id}")
    b.button(text="❌ Отклонить", callback_data=f"reject:{post_id}")
    b.button(text="👤 Профиль", callback_data=f"profile:{user_id}")
    b.button(text="🔨 Бан", callback_data=f"ban:{user_id}")
    b.button(text="🔇 Мут", callback_data=f"mute:{user_id}")
    b.adjust(2, 2, 1)
    return b.as_markup()


def profile_keyboard(user_id: int, banned: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if banned:
        b.button(text="✅ Разбанить", callback_data=f"unban:{user_id}")
    else:
        b.button(text="🔨 Бан", callback_data=f"ban:{user_id}")
    b.button(text="🔇 Мут", callback_data=f"mute:{user_id}")
    b.button(text="🗑 Скрыть", callback_data="hide")
    b.adjust(2, 1)
    return b.as_markup()


def mute_menu(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    options = (
        ("1 час", 3600),
        ("6 часов", 6 * 3600),
        ("1 день", 24 * 3600),
        ("7 дней", 7 * 24 * 3600),
    )
    for label, seconds in options:
        b.button(text=label, callback_data=f"mute_set:{user_id}:{seconds}")
    b.button(text="🔙 Назад", callback_data=f"profile:{user_id}")
    b.adjust(4, 1)
    return b.as_markup()
