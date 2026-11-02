"""Глобальный контекст приложения: БД и конфиг.

Хранится в одном месте, чтобы обработчики (в т.ч. фоновые задачи для
медиагрупп) имели доступ к базе и настройкам без циклических импортов.
"""
from __future__ import annotations

from typing import Optional

from config import Config
from database import Database

db: Optional[Database] = None
cfg: Optional[Config] = None


def init(database: Database, config: Config) -> None:
    global db, cfg
    db = database
    cfg = config
