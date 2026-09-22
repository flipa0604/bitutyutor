"""SQLite persistence layer (aiosqlite, no ORM)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from .models import RESIDENCE_VALUES, BotUser, FullProfile, Group, Student, TestUser, Tutor

_RESIDENCE_CHECK = "CHECK (residence IN ({}))".format(",".join(f"'{v}'" for v in RESIDENCE_VALUES))
"""The ``students.residence`` constraint, spelled from :data:`RESIDENCE_VALUES`. SQLite cannot
alter a CHECK in place, so a table whose stored constraint no longer contains this text is rebuilt
in :meth:`Database.init` -- that is what lets a new code be added by appending it to the tuple."""

_STUDENTS_COLUMNS = f"""
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  tutor_id INTEGER NOT NULL REFERENCES tutors(id) ON DELETE CASCADE,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  direction TEXT NOT NULL,
  residence TEXT NOT NULL {_RESIDENCE_CHECK},
  address TEXT NOT NULL,
  father_name TEXT NOT NULL,
  father_phone TEXT NOT NULL,
  mother_name TEXT NOT NULL,
  mother_phone TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  edited_at TEXT
"""

_STUDENT_COLUMN_NAMES = (
    "id, telegram_id, username, tutor_id, group_id, full_name, phone, direction, residence, address,"
    " father_name, father_phone, mother_name, mother_phone, created_at, updated_at, edited_at"
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
  telegram_id INTEGER PRIMARY KEY,
  username TEXT,
  full_name TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  last_start_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS test_users (
  telegram_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
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
CREATE TABLE IF NOT EXISTS students ({_STUDENTS_COLUMNS});
CREATE TABLE IF NOT EXISTS full_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  tutor_id INTEGER NOT NULL REFERENCES tutors(id) ON DELETE CASCADE,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  direction TEXT NOT NULL,
  course INTEGER NOT NULL,
  passport TEXT NOT NULL,
  pinfl TEXT NOT NULL,
  birth_date TEXT NOT NULL,
  citizenship TEXT NOT NULL,
  region TEXT NOT NULL,
  district TEXT NOT NULL,
  mfy TEXT NOT NULL,
  mfy_contact TEXT NOT NULL,
  street TEXT NOT NULL,
  employed INTEGER NOT NULL DEFAULT 0,
  work_place TEXT NOT NULL DEFAULT '',
  work_position TEXT NOT NULL DEFAULT '',
  work_address TEXT NOT NULL DEFAULT '',
  work_phone TEXT NOT NULL DEFAULT '',
  married INTEGER NOT NULL DEFAULT 0,
  spouse_name TEXT NOT NULL DEFAULT '',
  spouse_work TEXT NOT NULL DEFAULT '',
  spouse_phone TEXT NOT NULL DEFAULT '',
  social_status TEXT NOT NULL DEFAULT '',
  father_name TEXT NOT NULL,
  father_phone TEXT NOT NULL,
  father_work TEXT NOT NULL,
  mother_name TEXT NOT NULL,
  mother_phone TEXT NOT NULL,
  mother_work TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  edited_at TEXT
);
-- One passport and one PNFL can belong to one person only: the cheapest guard against a student
-- filling the survey twice under made-up identities.
CREATE UNIQUE INDEX IF NOT EXISTS full_profiles_passport ON full_profiles(passport);
CREATE UNIQUE INDEX IF NOT EXISTS full_profiles_pinfl ON full_profiles(pinfl);
"""

# The documented way to change a constraint in SQLite: build the table afresh, copy the rows over
# (ids included, so nothing referring to a student changes), swap the names. Foreign keys are off
# for the duration as the docs prescribe; the pragma only takes effect outside a transaction, which
# is why it brackets the explicit BEGIN/COMMIT instead of sitting inside it. The AUTOINCREMENT
# counter is carried over too, otherwise it would restart at the highest surviving id and hand a
# deleted student's id to the next one; DROP TABLE removes the old counter and RENAME keeps the new.
_REBUILD_STUDENTS = f"""
PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE students_new ({_STUDENTS_COLUMNS});
INSERT INTO students_new ({_STUDENT_COLUMN_NAMES}) SELECT {_STUDENT_COLUMN_NAMES} FROM students;
INSERT INTO sqlite_sequence (name, seq)
  SELECT 'students_new', 0 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'students_new');
UPDATE sqlite_sequence
  SET seq = MAX(seq, COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'students'), 0))
  WHERE name = 'students_new';
DROP TABLE students;
ALTER TABLE students_new RENAME TO students;
COMMIT;
PRAGMA foreign_keys = ON;
"""

_STUDENT_SELECT = """
SELECT s.*, t.name AS tutor_name, g.name AS group_name
FROM students s
JOIN tutors t ON t.id = s.tutor_id
JOIN groups g ON g.id = s.group_id
"""

_GROUP_SELECT = """
SELECT g.*,
       (SELECT COUNT(*) FROM students s WHERE s.group_id = g.id) AS student_count,
       (SELECT COUNT(*) FROM full_profiles f WHERE f.group_id = g.id) AS profile_count
FROM groups g
"""

_FULL_SELECT = """
SELECT f.*, t.name AS tutor_name, t.phone AS tutor_phone, g.name AS group_name
FROM full_profiles f
JOIN tutors t ON t.id = f.tutor_id
JOIN groups g ON g.id = f.group_id
"""

_USER_SELECT = """
SELECT u.*, (EXISTS(SELECT 1 FROM students s WHERE s.telegram_id = u.telegram_id)
             OR EXISTS(SELECT 1 FROM full_profiles f WHERE f.telegram_id = u.telegram_id)) AS is_student
FROM users u
"""

_TEST_USER_SELECT = """
SELECT t.telegram_id, t.created_at, u.username AS username,
       COALESCE(NULLIF(u.full_name, ''), t.name) AS name
FROM test_users t
LEFT JOIN users u ON u.telegram_id = t.telegram_id
"""

_BACKFILL_USERS = """
INSERT OR IGNORE INTO users (telegram_id, username, full_name, started_at, last_start_at)
SELECT telegram_id, username, full_name, created_at, updated_at FROM students
"""


STUDENT_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "tutor_id",
        "group_id",
        "username",
        "full_name",
        "phone",
        "direction",
        "residence",
        "address",
        "father_name",
        "father_phone",
        "mother_name",
        "mother_phone",
    }
)
"""Columns :meth:`Database.update_student` may write; ``id``, ``telegram_id`` and the timestamps
are immutable. Only names from this set are ever interpolated into an UPDATE statement."""


class DuplicateError(sqlite3.IntegrityError):
    """A UNIQUE constraint was violated (duplicate tutor telegram_id or duplicate group name)."""


def _row_to_tutor(row: aiosqlite.Row) -> Tutor:
    return Tutor(
        id=row["id"],
        name=row["name"],
        telegram_id=row["telegram_id"],
        created_at=row["created_at"],
        phone=row["phone"] or "",
    )


async def _existing_columns(conn: aiosqlite.Connection, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row["name"] for row in await cur.fetchall()}


async def _table_sql(conn: aiosqlite.Connection, table: str) -> str:
    """The ``CREATE TABLE`` text SQLite keeps for ``table`` (empty when there is no such table)."""
    async with conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)) as cur:
        row = await cur.fetchone()
    return str(row["sql"]) if row else ""


def _row_to_test_user(row: aiosqlite.Row) -> TestUser:
    return TestUser(
        telegram_id=row["telegram_id"],
        name=row["name"],
        created_at=row["created_at"],
        username=row["username"],
    )


def _row_to_bot_user(row: aiosqlite.Row) -> BotUser:
    return BotUser(
        telegram_id=row["telegram_id"],
        username=row["username"],
        full_name=row["full_name"],
        started_at=row["started_at"],
        last_start_at=row["last_start_at"],
        is_student=bool(row["is_student"]),
    )


def _row_to_group(row: aiosqlite.Row) -> Group:
    return Group(
        id=row["id"],
        tutor_id=row["tutor_id"],
        name=row["name"],
        created_at=row["created_at"],
        student_count=row["student_count"],
        profile_count=row["profile_count"],
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
        edited_at=row["edited_at"],
        tutor_name=row["tutor_name"],
        group_name=row["group_name"],
    )


_FULL_COLUMNS: tuple[str, ...] = (
    "telegram_id", "username", "tutor_id", "group_id", "full_name", "phone", "direction", "course",
    "passport", "pinfl", "birth_date", "citizenship", "region", "district", "mfy", "mfy_contact",
    "street", "employed", "work_place", "work_position", "work_address", "work_phone", "married",
    "spouse_name", "spouse_work", "spouse_phone", "social_status", "father_name", "father_phone",
    "father_work", "mother_name", "mother_phone", "mother_work",
)
"""Every writable column of ``full_profiles``, in insert order."""

FULL_EDITABLE_FIELDS: frozenset[str] = frozenset(set(_FULL_COLUMNS) - {"telegram_id"})
"""Columns :meth:`Database.update_full_profile` may write; only names from this set are ever
interpolated into an UPDATE statement, the values stay bound parameters."""


def _row_to_full(row: aiosqlite.Row) -> FullProfile:
    values: dict[str, Any] = {name: row[name] for name in _FULL_COLUMNS}
    values["employed"] = bool(values["employed"])
    values["married"] = bool(values["married"])
    values["course"] = int(values["course"])
    return FullProfile(
        id=row["id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        edited_at=row["edited_at"],
        tutor_name=row["tutor_name"],
        tutor_phone=row["tutor_phone"] or "",
        group_name=row["group_name"],
        **values,
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
        # ``CREATE TABLE IF NOT EXISTS`` never alters a table that is already there, so columns
        # added after the first release have to be brought in explicitly.
        if "edited_at" not in await _existing_columns(conn, "students"):
            await conn.execute("ALTER TABLE students ADD COLUMN edited_at TEXT")
        # The tutor's own phone number, a column of the full survey, arrived with it.
        if "phone" not in await _existing_columns(conn, "tutors"):
            await conn.execute("ALTER TABLE tutors ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        # A residence code added after the table was created is rejected by the stored CHECK
        # constraint until the table is rebuilt with the current one (after the column above, which
        # the copy needs). ``executescript`` commits whatever is pending first, so the pragma works.
        if _RESIDENCE_CHECK not in await _table_sql(conn, "students"):
            await conn.executescript(_REBUILD_STUDENTS)
        # Students saved before the users table existed have obviously pressed /start, so seed them
        # instead of showing a half-empty list until each of them happens to come back.
        await conn.execute(_BACKFILL_USERS)
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

    # -------------------------------------------------------------------- users

    async def touch_user(self, telegram_id: int, username: str | None, full_name: str) -> None:
        """Record a /start press: the first one creates the row, later ones refresh the profile."""
        await self._write(
            """
            INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
              username = excluded.username,
              full_name = excluded.full_name,
              last_start_at = datetime('now','localtime')
            """,
            (telegram_id, username, full_name),
        )

    async def count_users(self) -> tuple[int, int]:
        """``(total, registered)``: how many people started the bot, and how many are students."""
        row = await self._fetchone(
            "SELECT COUNT(*) AS total,"
            " SUM(EXISTS(SELECT 1 FROM students s WHERE s.telegram_id = u.telegram_id)"
            "     OR EXISTS(SELECT 1 FROM full_profiles f WHERE f.telegram_id = u.telegram_id)) AS registered"
            " FROM users u"
        )
        if row is None:
            return 0, 0
        return int(row["total"] or 0), int(row["registered"] or 0)

    async def list_users(self, limit: int, offset: int = 0) -> list[BotUser]:
        """One page of users, oldest first, so the numbering stays stable as new ones arrive."""
        rows = await self._fetchall(
            _USER_SELECT + " ORDER BY u.started_at, u.telegram_id LIMIT ? OFFSET ?", (limit, offset)
        )
        return [_row_to_bot_user(r) for r in rows]

    async def list_user_ids(self) -> list[int]:
        """Telegram ids of everyone who ever pressed /start -- the audience of a broadcast."""
        rows = await self._fetchall("SELECT telegram_id FROM users ORDER BY started_at, telegram_id")
        return [int(r["telegram_id"]) for r in rows]

    # -------------------------------------------------------------- test users

    async def add_test_user(self, telegram_id: int, name: str = "") -> bool:
        """Put a Telegram ID on the tester list. ``False`` when it was already there."""
        try:
            await self._write("INSERT INTO test_users (telegram_id, name) VALUES (?, ?)", (telegram_id, name))
        except DuplicateError:
            return False
        return True

    async def remove_test_user(self, telegram_id: int) -> bool:
        cur = await self._write("DELETE FROM test_users WHERE telegram_id = ?", (telegram_id,))
        return cur.rowcount > 0

    async def is_test_user(self, telegram_id: int) -> bool:
        return await self._fetchone("SELECT 1 FROM test_users WHERE telegram_id = ?", (telegram_id,)) is not None

    async def list_test_users(self) -> list[TestUser]:
        rows = await self._fetchall(_TEST_USER_SELECT + " ORDER BY t.created_at, t.telegram_id")
        return [_row_to_test_user(r) for r in rows]

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

    async def count_tutor_groups_and_students(self, tutor_id: int) -> tuple[int, int, int]:
        """``(groups, basic-survey students, full-survey students)`` -- the two surveys are counted
        apart, because a student may have filled either one without the other."""
        row = await self._fetchone(
            "SELECT (SELECT COUNT(*) FROM groups WHERE tutor_id = ?) AS groups_n,"
            " (SELECT COUNT(*) FROM students WHERE tutor_id = ?) AS students_n,"
            " (SELECT COUNT(*) FROM full_profiles WHERE tutor_id = ?) AS profiles_n",
            (tutor_id, tutor_id, tutor_id),
        )
        assert row is not None
        return int(row["groups_n"]), int(row["students_n"]), int(row["profiles_n"])

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
                  updated_at = datetime('now','localtime'),
                  edited_at = datetime('now','localtime')
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

    async def update_student(self, telegram_id: int, /, **fields: Any) -> Student | None:
        """Overwrite single columns of one student, bump ``updated_at`` and return the fresh row.

        Returns ``None`` when no row matched, i.e. the registration is gone (deleted by staff, or the
        student's tutor or group was deleted mid-edit and cascaded). Field names are checked against
        ``STUDENT_EDITABLE_FIELDS`` before they reach the statement, so the interpolation below
        cannot carry caller input into the SQL; the values stay bound parameters.

        ``telegram_id`` is positional-only so that a caller passing ``telegram_id=...`` among the
        fields gets the whitelist's error rather than a confusing TypeError.
        """
        if not fields:
            raise ValueError("update_student() needs at least one field")
        unknown = sorted(set(fields) - STUDENT_EDITABLE_FIELDS)
        if unknown:
            raise ValueError(f"Not an editable student field: {', '.join(unknown)}")
        if "residence" in fields and fields["residence"] not in RESIDENCE_VALUES:
            raise ValueError(f"Invalid residence: {fields['residence']!r}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        cur = await self._write(
            f"UPDATE students SET {assignments}, updated_at = datetime('now','localtime'),"
            " edited_at = datetime('now','localtime') WHERE telegram_id = ?",
            (*fields.values(), telegram_id),
        )
        if cur.rowcount == 0:
            return None
        return await self.get_student_by_telegram_id(telegram_id)

    async def get_student_by_telegram_id(self, telegram_id: int) -> Student | None:
        row = await self._fetchone(_STUDENT_SELECT + " WHERE s.telegram_id = ?", (telegram_id,))
        return _row_to_student(row) if row else None

    async def get_student(self, student_id: int) -> Student | None:
        row = await self._fetchone(_STUDENT_SELECT + " WHERE s.id = ?", (student_id,))
        return _row_to_student(row) if row else None

    async def delete_student(self, student_id: int, tutor_id: int | None = None) -> bool:
        """Remove one registration for good; with ``tutor_id`` only if the student still belongs to that
        tutor, so the ownership check and the delete are one statement (no window for the student to
        move to another tutor in between). ``False`` when nothing matched: already deleted, or moved."""
        cur = await self._write(
            "DELETE FROM students WHERE id = ? AND (? IS NULL OR tutor_id = ?)", (student_id, tutor_id, tutor_id)
        )
        return cur.rowcount > 0

    # ----------------------------------------------------------- full survey

    async def upsert_full_profile(self, *, telegram_id: int, **fields: Any) -> tuple[FullProfile, bool]:
        """Insert or replace the full-survey row of ``telegram_id``; returns ``(profile, is_update)``.

        A passport or PNFL already used by *another* student raises :class:`DuplicateError`, so one
        person cannot be entered twice under made-up identities.
        """
        unknown = sorted(set(fields) - set(_FULL_COLUMNS))
        if unknown:
            raise ValueError(f"Not a full-profile field: {', '.join(unknown)}")
        missing = sorted(set(_FULL_COLUMNS) - {"telegram_id"} - set(fields))
        if missing:
            raise ValueError(f"Missing full-profile fields: {', '.join(missing)}")
        group = await self.get_group(int(fields["group_id"]))
        if group is None or group.tutor_id != int(fields["tutor_id"]):
            raise ValueError("Group does not exist or does not belong to the tutor")
        values: dict[str, Any] = {"telegram_id": telegram_id, **fields}
        values["employed"] = int(bool(values["employed"]))
        values["married"] = int(bool(values["married"]))
        columns = ", ".join(_FULL_COLUMNS)
        placeholders = ", ".join("?" for _ in _FULL_COLUMNS)
        assignments = ", ".join(f"{name} = excluded.{name}" for name in _FULL_COLUMNS if name != "telegram_id")
        async with self._lock:
            # Existence check and write must not interleave with another upsert of the same student,
            # otherwise both callers would report a brand-new registration (see ``upsert_student``).
            row = await self._fetchone_unlocked("SELECT 1 FROM full_profiles WHERE telegram_id = ?", (telegram_id,))
            is_update = row is not None
            await self._write_unlocked(
                f"""
                INSERT INTO full_profiles ({columns}) VALUES ({placeholders})
                ON CONFLICT(telegram_id) DO UPDATE SET
                  {assignments},
                  updated_at = datetime('now','localtime'),
                  edited_at = datetime('now','localtime')
                """,
                tuple(values[name] for name in _FULL_COLUMNS),
            )
        profile = await self.get_full_profile_by_telegram_id(telegram_id)
        assert profile is not None
        return profile, is_update

    async def update_full_profile(self, telegram_id: int, /, **fields: Any) -> FullProfile | None:
        """Overwrite single columns, bump ``updated_at``/``edited_at`` and return the fresh row."""
        if not fields:
            raise ValueError("update_full_profile() needs at least one field")
        unknown = sorted(set(fields) - FULL_EDITABLE_FIELDS)
        if unknown:
            raise ValueError(f"Not an editable full-profile field: {', '.join(unknown)}")
        values = dict(fields)
        for flag in ("employed", "married"):
            if flag in values:
                values[flag] = int(bool(values[flag]))
        assignments = ", ".join(f"{name} = ?" for name in values)
        cur = await self._write(
            f"UPDATE full_profiles SET {assignments}, updated_at = datetime('now','localtime'),"
            " edited_at = datetime('now','localtime') WHERE telegram_id = ?",
            (*values.values(), telegram_id),
        )
        if cur.rowcount == 0:
            return None
        return await self.get_full_profile_by_telegram_id(telegram_id)

    async def get_full_profile_by_telegram_id(self, telegram_id: int) -> FullProfile | None:
        row = await self._fetchone(_FULL_SELECT + " WHERE f.telegram_id = ?", (telegram_id,))
        return _row_to_full(row) if row else None

    async def get_full_profile(self, profile_id: int) -> FullProfile | None:
        row = await self._fetchone(_FULL_SELECT + " WHERE f.id = ?", (profile_id,))
        return _row_to_full(row) if row else None

    async def delete_full_profile(self, profile_id: int, tutor_id: int | None = None) -> bool:
        """Remove one full-survey row; with ``tutor_id`` only while it still belongs to that tutor."""
        cur = await self._write(
            "DELETE FROM full_profiles WHERE id = ? AND (? IS NULL OR tutor_id = ?)",
            (profile_id, tutor_id, tutor_id),
        )
        return cur.rowcount > 0

    async def list_full_profiles(
        self, tutor_id: int | None = None, group_id: int | None = None
    ) -> list[FullProfile]:
        """Full-survey rows joined with tutor/group names, ordered by group then name."""
        conditions: list[str] = []
        params: list[Any] = []
        if tutor_id is not None:
            conditions.append("f.tutor_id = ?")
            params.append(tutor_id)
        if group_id is not None:
            conditions.append("f.group_id = ?")
            params.append(group_id)
        sql = _FULL_SELECT
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY g.name COLLATE NOCASE, f.full_name COLLATE NOCASE, f.id"
        rows = await self._fetchall(sql, tuple(params))
        return [_row_to_full(r) for r in rows]

    async def count_group_profiles(self, group_id: int) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS n FROM full_profiles WHERE group_id = ?", (group_id,))
        assert row is not None
        return int(row["n"])

    async def find_full_profile_owner(self, *, passport: str, pinfl: str) -> int | None:
        """Telegram id of whoever already holds this passport or PNFL (``None`` when nobody does)."""
        row = await self._fetchone(
            "SELECT telegram_id FROM full_profiles WHERE passport = ? OR pinfl = ?", (passport, pinfl)
        )
        return int(row["telegram_id"]) if row else None

    async def update_tutor_phone(self, tutor_id: int, phone: str) -> bool:
        cur = await self._write("UPDATE tutors SET phone = ? WHERE id = ?", (phone, tutor_id))
        return cur.rowcount > 0

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
