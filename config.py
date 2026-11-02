"""Загрузка настроек из переменных окружения (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> list[int]:
    """Разобрать строку '1, 2, 3' в список целых чисел (только положительные)."""
    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


@dataclass
class Config:
    bot_token: str
    admin_ids: list[int] = field(default_factory=list)
    channel_id: int = 0
    moderation_chat_id: int = 0
    proxy_url: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "BOT_TOKEN не задан. Скопируй .env.example в .env и заполни его."
            )

        channel_id = int(os.getenv("CHANNEL_ID", "0") or 0)
        moderation_chat_id = int(os.getenv("MODERATION_CHAT_ID", "0") or 0)

        return cls(
            bot_token=token,
            admin_ids=_parse_ids(os.getenv("ADMIN_IDS", "")),
            channel_id=channel_id,
            moderation_chat_id=moderation_chat_id,
            proxy_url=os.getenv("TELEGRAM_PROXY", "").strip(),
        )
