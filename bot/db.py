"""SQLite persistence layer (aiosqlite, no ORM)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from .models import RESIDENCE_VALUES, Group, Student, Tutor

SCHEMA = """
CREATE TABLE IF NOT EXISTS tutors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  telegram_id INTEGER NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tutor_id INTEGER NOT NULL REFERENCES tutors(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE(tutor_id, name)
);
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  tutor_id INTEGER NOT NULL REFERENCES tutors(id) ON DELETE CASCADE,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  direction TEXT NOT NULL,
  residence TEXT NOT NULL CHECK (residence IN ('ttj','kvartira','uy')),
  address TEXT NOT NULL,
  father_name TEXT NOT NULL,
  father_phone TEXT NOT NULL,
  mother_name TEXT NOT NULL,
  mother_phone TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

_STUDENT_SELECT = """
SELECT s.*, t.name AS tutor_name, g.name AS group_name
FROM students s
JOIN tutors t ON t.id = s.tutor_id
JOIN groups g ON g.id = s.group_id
"""

_GROUP_SELECT = """
SELECT g.*, (SELECT COUNT(*) FROM students s WHERE s.group_id = g.id) AS student_count
FROM groups g
"""


class DuplicateError(sqlite3.IntegrityError):
    """A UNIQUE constraint was violated (duplicate tutor telegram_id or duplicate group name)."""


def _row_to_tutor(row: aiosqlite.Row) -> Tutor:
    return Tutor(id=row["id"], name=row["name"], telegram_id=row["telegram_id"], created_at=row["created_at"])


def _row_to_group(row: aiosqlite.Row) -> Group:
    return Group(
        id=row["id"],
        tutor_id=row["tutor_id"],
        name=row["name"],
        created_at=row["created_at"],
        student_count=row["student_count"],
    )


def _row_to_student(row: aiosqlite.Row) -> Student:
    return Student(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        tutor_id=row["tutor_id"],
        group_id=row["group_id"],
        full_name=row["full_name"],
        phone=row["phone"],
        direction=row["direction"],
        residence=row["residence"],
        address=row["address"],
        father_name=row["father_name"],
        father_phone=row["father_phone"],
        mother_name=row["mother_name"],
        mother_phone=row["mother_phone"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        tutor_name=row["tutor_name"],
        group_name=row["group_name"],
    )


class Database:
    """Async wrapper around a single aiosqlite connection.

    Handlers run concurrently (aiogram dispatches every update as its own task) but share this one
    connection, which uses sqlite3's implicit transactions. Every statement is therefore serialised
    with ``_lock``, because a ``commit()``/``rollback()`` on this connection hits whatever any other
    coroutine has in flight: it would discard another coroutine's not-yet-committed write, and it
    also invalidates a cursor opened by a concurrent read, which fails between ``execute()`` and
    ``fetchone()`` with "Cursor needed to be reset because of commit/rollback". Callers that already
    hold the lock use the ``*_unlocked`` helpers -- ``asyncio.Lock`` is not reentrant.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not initialised; call `await db.init()` first")
        return self._conn

    async def init(self) -> None:
        """Open the connection, enable foreign keys and create the schema."""
        if self._conn is not None:
            return
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.executescript(SCHEMA)
        await conn.commit()
        self._conn = conn

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ helpers

    async def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self._lock:
            return await self._fetchone_unlocked(sql, params)

    async def _fetchone_unlocked(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        """``_fetchone`` body for callers that already hold ``_lock``."""
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return list(await cur.fetchall())

    async def _write(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        """Execute a mutating statement and commit; translate UNIQUE violations to DuplicateError."""
        async with self._lock:
            return await self._write_unlocked(sql, params)

    async def _write_unlocked(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        """``_write`` body for callers that already hold ``_lock``."""
        try:
            cur = await self.conn.execute(sql, params)
            await self.conn.commit()
        except sqlite3.IntegrityError as exc:
            await self.conn.rollback()
            if "UNIQUE" in str(exc).upper():
                raise DuplicateError(str(exc)) from exc
            raise
        return cur

    # ------------------------------------------------------------------- tutors

    async def add_tutor(self, name: str, telegram_id: int) -> Tutor:
        cur = await self._write("INSERT INTO tutors (name, telegram_id) VALUES (?, ?)", (name, telegram_id))
        tutor = await self.get_tutor(int(cur.lastrowid or 0))
        assert tutor is not None
        return tutor

    async def get_tutor(self, tutor_id: int) -> Tutor | None:
        row = await self._fetchone("SELECT * FROM tutors WHERE id = ?", (tutor_id,))
        return _row_to_tutor(row) if row else None

    async def get_tutor_by_telegram_id(self, telegram_id: int) -> Tutor | None:
        row = await self._fetchone("SELECT * FROM tutors WHERE telegram_id = ?", (telegram_id,))
        return _row_to_tutor(row) if row else None

    async def list_tutors(self) -> list[Tutor]:
        rows = await self._fetchall("SELECT * FROM tutors ORDER BY name COLLATE NOCASE, id")
        return [_row_to_tutor(r) for r in rows]

    async def update_tutor_name(self, tutor_id: int, name: str) -> bool:
        cur = await self._write("UPDATE tutors SET name = ? WHERE id = ?", (name, tutor_id))
        return cur.rowcount > 0

    async def update_tutor_telegram_id(self, tutor_id: int, telegram_id: int) -> bool:
        cur = await self._write("UPDATE tutors SET telegram_id = ? WHERE id = ?", (telegram_id, tutor_id))
        return cur.rowcount > 0

    async def delete_tutor(self, tutor_id: int) -> bool:
        cur = await self._write("DELETE FROM tutors WHERE id = ?", (tutor_id,))
        return cur.rowcount > 0

    async def count_tutor_groups_and_students(self, tutor_id: int) -> tuple[int, int]:
        row = await self._fetchone(
            "SELECT (SELECT COUNT(*) FROM groups WHERE tutor_id = ?) AS groups_n,"
            " (SELECT COUNT(*) FROM students WHERE tutor_id = ?) AS students_n",
            (tutor_id, tutor_id),
        )
        assert row is not None
        return int(row["groups_n"]), int(row["students_n"])

    # ------------------------------------------------------------------- groups

    async def add_group(self, tutor_id: int, name: str) -> Group:
        cur = await self._write("INSERT INTO groups (tutor_id, name) VALUES (?, ?)", (tutor_id, name))
        group = await self.get_group(int(cur.lastrowid or 0))
        assert group is not None
        return group

    async def get_group(self, group_id: int) -> Group | None:
        row = await self._fetchone(_GROUP_SELECT + " WHERE g.id = ?", (group_id,))
        return _row_to_group(row) if row else None

    async def list_groups(self, tutor_id: int) -> list[Group]:
        rows = await self._fetchall(
            _GROUP_SELECT + " WHERE g.tutor_id = ? ORDER BY g.name COLLATE NOCASE, g.id", (tutor_id,)
        )
        return [_row_to_group(r) for r in rows]

    async def rename_group(self, group_id: int, name: str) -> bool:
        cur = await self._write("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
        return cur.rowcount > 0

    async def delete_group(self, group_id: int) -> bool:
        cur = await self._write("DELETE FROM groups WHERE id = ?", (group_id,))
        return cur.rowcount > 0

    async def count_group_students(self, group_id: int) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS n FROM students WHERE group_id = ?", (group_id,))
        assert row is not None
        return int(row["n"])

    # ----------------------------------------------------------------- students

    async def upsert_student(
        self,
        *,
        telegram_id: int,
        username: str | None,
        tutor_id: int,
        group_id: int,
        full_name: str,
        phone: str,
        direction: str,
        residence: str,
        address: str,
        father_name: str,
        father_phone: str,
        mother_name: str,
        mother_phone: str,
    ) -> tuple[Student, bool]:
        """Insert or replace the student identified by ``telegram_id``.

        Returns ``(student, is_update)``; on update ``created_at`` is kept and ``updated_at`` bumped.
        """
        if residence not in RESIDENCE_VALUES:
            raise ValueError(f"Invalid residence: {residence!r}")
        group = await self.get_group(group_id)
        if group is None or group.tutor_id != tutor_id:
            raise ValueError("Group does not exist or does not belong to the tutor")
        async with self._lock:
            # The existence check and the write must not interleave with another upsert of the same
            # student, otherwise both callers would report a brand-new registration.
            row = await self._fetchone_unlocked("SELECT 1 FROM students WHERE telegram_id = ?", (telegram_id,))
            is_update = row is not None
            await self._write_unlocked(
                """
                INSERT INTO students (
                  telegram_id, username, tutor_id, group_id, full_name, phone, direction,
                  residence, address, father_name, father_phone, mother_name, mother_phone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                  username = excluded.username,
                  tutor_id = excluded.tutor_id,
                  group_id = excluded.group_id,
                  full_name = excluded.full_name,
                  phone = excluded.phone,
                  direction = excluded.direction,
                  residence = excluded.residence,
                  address = excluded.address,
                  father_name = excluded.father_name,
                  father_phone = excluded.father_phone,
                  mother_name = excluded.mother_name,
                  mother_phone = excluded.mother_phone,
                  updated_at = datetime('now','localtime')
                """,
                (
                    telegram_id,
                    username,
                    tutor_id,
                    group_id,
                    full_name,
                    phone,
                    direction,
                    residence,
                    address,
                    father_name,
                    father_phone,
                    mother_name,
                    mother_phone,
                ),
            )
        student = await self.get_student_by_telegram_id(telegram_id)
        assert student is not None
        return student, is_update

    async def get_student_by_telegram_id(self, telegram_id: int) -> Student | None:
        row = await self._fetchone(_STUDENT_SELECT + " WHERE s.telegram_id = ?", (telegram_id,))
        return _row_to_student(row) if row else None

    async def list_students(
        self,
        tutor_id: int | None = None,
        group_id: int | None = None,
        residence: str | None = None,
    ) -> list[Student]:
        """Students joined with tutor/group names, ordered by group name then full name."""
        conditions: list[str] = []
        params: list[Any] = []
        if tutor_id is not None:
            conditions.append("s.tutor_id = ?")
            params.append(tutor_id)
        if group_id is not None:
            conditions.append("s.group_id = ?")
            params.append(group_id)
        if residence is not None:
            conditions.append("s.residence = ?")
            params.append(residence)
        sql = _STUDENT_SELECT
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY g.name COLLATE NOCASE, s.full_name COLLATE NOCASE, s.id"
        rows = await self._fetchall(sql, tuple(params))
        return [_row_to_student(r) for r in rows]
