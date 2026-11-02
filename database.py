"""SQLite-хранилище: пользователи и посты."""
from __future__ import annotations

import time
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent / "data" / "bot.db"


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self._create_tables()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def _create_tables(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                last_name  TEXT,
                banned     INTEGER NOT NULL DEFAULT 0,
                mute_until INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                post_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                text         TEXT,
                media_json   TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                created_at   INTEGER NOT NULL,
                reviewed_at  INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
            """
        )
        await self.conn.commit()

    # ---------- низкоуровневые помощники ----------
    async def _fetchone(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchall()

    async def _execute(self, sql: str, params: tuple = ()):
        await self.conn.execute(sql, params)
        await self.conn.commit()

    # ---------- пользователи ----------
    async def get_or_create_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ):
        row = await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            await self._execute(
                "INSERT INTO users (user_id, username, first_name, last_name, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, first_name, last_name, int(time.time())),
            )
            row = await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        else:
            await self._execute(
                "UPDATE users SET username = ?, first_name = ?, last_name = ? WHERE user_id = ?",
                (username, first_name, last_name, user_id),
            )
        return row

    async def get_user(self, user_id: int):
        return await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))

    async def set_ban(self, user_id: int, banned: bool) -> None:
        await self._execute(
            "UPDATE users SET banned = ? WHERE user_id = ?", (1 if banned else 0, user_id)
        )

    async def set_mute(self, user_id: int, until: int) -> None:
        await self._execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (until, user_id))

    async def is_banned(self, user_id: int) -> bool:
        row = await self._fetchone("SELECT banned FROM users WHERE user_id = ?", (user_id,))
        return bool(row and row["banned"])

    async def mute_until(self, user_id: int) -> int:
        row = await self._fetchone("SELECT mute_until FROM users WHERE user_id = ?", (user_id,))
        return row["mute_until"] if row else 0

    # ---------- посты ----------
    async def create_post(
        self, user_id: int, content_type: str, text: str | None, media_json: str | None
    ) -> int:
        await self._execute(
            "INSERT INTO posts (user_id, content_type, text, media_json, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (user_id, content_type, text, media_json, int(time.time())),
        )
        cur = await self.conn.execute("SELECT last_insert_rowid() AS id")
        row = await cur.fetchone()
        return row["id"]

    async def get_post(self, post_id: int):
        return await self._fetchone("SELECT * FROM posts WHERE post_id = ?", (post_id,))

    async def set_post_status(self, post_id: int, status: str) -> None:
        await self._execute(
            "UPDATE posts SET status = ?, reviewed_at = ? WHERE post_id = ?",
            (status, int(time.time()), post_id),
        )

    async def user_post_stats(self, user_id: int) -> dict:
        rows = await self._fetchall(
            "SELECT status, COUNT(*) AS c FROM posts WHERE user_id = ? GROUP BY status",
            (user_id,),
        )
        result = {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
        for row in rows:
            result[row["status"]] = row["c"]
            result["total"] += row["c"]
        return result

    async def stats(self) -> dict:
        async def count(sql: str, params: tuple = ()) -> int:
            row = await self._fetchone(sql, params)
            return row["c"] if row else 0

        now = int(time.time())
        return {
            "users": await count("SELECT COUNT(*) AS c FROM users"),
            "posts": await count("SELECT COUNT(*) AS c FROM posts"),
            "pending": await count("SELECT COUNT(*) AS c FROM posts WHERE status = 'pending'"),
            "approved": await count("SELECT COUNT(*) AS c FROM posts WHERE status = 'approved'"),
            "rejected": await count("SELECT COUNT(*) AS c FROM posts WHERE status = 'rejected'"),
            "banned": await count("SELECT COUNT(*) AS c FROM users WHERE banned = 1"),
            "muted": await count("SELECT COUNT(*) AS c FROM users WHERE mute_until > ?", (now,)),
        }
