"""Database layer: tutor/group CRUD, uniqueness, cascades, student upsert/edit, users and filters."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bot.db import Database, DuplicateError
from bot.models import Student


def student_kwargs(telegram_id: int, tutor_id: int, group_id: int, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "telegram_id": telegram_id,
        "username": f"user{telegram_id}",
        "tutor_id": tutor_id,
        "group_id": group_id,
        "full_name": f"Talaba {telegram_id}",
        "phone": "+998901234567",
        "direction": "Dasturiy injiniring",
        "residence": "ttj",
        "address": "TTJ",
        "father_name": "Ota Otayev",
        "father_phone": "+998901111111",
        "mother_name": "Ona Onayeva",
        "mother_phone": "+998902222222",
    }
    data.update(overrides)
    return data


async def test_tutor_crud(db: Database) -> None:
    tutor = await db.add_tutor("Karimov Aziz", 555)
    assert tutor.id > 0 and tutor.name == "Karimov Aziz" and tutor.telegram_id == 555
    assert tutor.created_at

    assert await db.get_tutor(tutor.id) == tutor
    assert await db.get_tutor_by_telegram_id(555) == tutor
    assert await db.get_tutor(999) is None
    assert await db.get_tutor_by_telegram_id(999) is None

    assert await db.update_tutor_name(tutor.id, "Karimov A.") is True
    assert await db.update_tutor_telegram_id(tutor.id, 556) is True
    updated = await db.get_tutor(tutor.id)
    assert updated is not None and updated.name == "Karimov A." and updated.telegram_id == 556
    assert await db.update_tutor_name(999, "x") is False

    await db.add_tutor("Aliyev Bobur", 777)
    assert [t.name for t in await db.list_tutors()] == ["Aliyev Bobur", "Karimov A."]

    assert await db.delete_tutor(tutor.id) is True
    assert await db.delete_tutor(tutor.id) is False
    assert await db.get_tutor(tutor.id) is None


async def test_tutor_telegram_id_unique(db: Database) -> None:
    await db.add_tutor("A", 1)
    with pytest.raises(DuplicateError):
        await db.add_tutor("B", 1)
    other = await db.add_tutor("B", 2)
    with pytest.raises(DuplicateError):
        await db.update_tutor_telegram_id(other.id, 1)
    # DuplicateError is still an IntegrityError for callers that catch the sqlite3 type
    with pytest.raises(sqlite3.IntegrityError):
        await db.add_tutor("C", 2)
    # the connection remains usable after a failed write
    assert len(await db.list_tutors()) == 2


async def test_group_crud_and_unique_per_tutor(db: Database) -> None:
    t1 = await db.add_tutor("T1", 1)
    t2 = await db.add_tutor("T2", 2)
    g1 = await db.add_group(t1.id, "DI-21")
    assert g1.tutor_id == t1.id and g1.name == "DI-21" and g1.student_count == 0

    with pytest.raises(DuplicateError):
        await db.add_group(t1.id, "DI-21")
    g_other = await db.add_group(t2.id, "DI-21")  # same name is fine for another tutor
    assert g_other.id != g1.id

    g2 = await db.add_group(t1.id, "AI-22")
    assert [g.name for g in await db.list_groups(t1.id)] == ["AI-22", "DI-21"]
    assert [g.name for g in await db.list_groups(t2.id)] == ["DI-21"]

    assert await db.rename_group(g2.id, "AI-23") is True
    with pytest.raises(DuplicateError):
        await db.rename_group(g2.id, "DI-21")
    renamed = await db.get_group(g2.id)
    assert renamed is not None and renamed.name == "AI-23"

    assert await db.delete_group(g2.id) is True
    assert await db.get_group(g2.id) is None
    assert await db.delete_group(g2.id) is False


async def test_upsert_student_and_counts(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")

    student, is_update = await db.upsert_student(**student_kwargs(100, tutor.id, group.id))
    assert is_update is False
    assert isinstance(student, Student)
    assert student.tutor_name == "T" and student.group_name == "G"
    assert student.created_at and student.updated_at

    again, is_update = await db.upsert_student(
        **student_kwargs(100, tutor.id, group.id, full_name="Yangi Ism", residence="uy", address="Toshkent")
    )
    assert is_update is True
    assert again.id == student.id
    assert again.full_name == "Yangi Ism" and again.residence == "uy" and again.address == "Toshkent"
    assert again.created_at == student.created_at

    assert await db.get_student_by_telegram_id(100) == again
    assert await db.get_student_by_telegram_id(101) is None
    assert await db.count_group_students(group.id) == 1
    assert await db.count_tutor_groups_and_students(tutor.id) == (1, 1)
    fetched = await db.get_group(group.id)
    assert fetched is not None and fetched.student_count == 1


async def test_concurrent_duplicate_rollback_does_not_discard_other_writes(db: Database) -> None:
    """A UNIQUE violation in one coroutine must never roll back another coroutine's write.

    Handlers run as concurrent tasks on one shared connection; before writes were serialised the
    duplicate's ``rollback()`` also threw away the concurrently queued INSERT/UPDATE.
    """
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    await db.add_group(tutor.id, "Old")

    results = await asyncio.gather(
        db.add_group(tutor.id, "G"),  # duplicate -> DuplicateError + rollback
        db.add_tutor("New", 99),
        db.add_group(tutor.id, "Fresh"),
        db.rename_group(group.id, "Renamed"),
        return_exceptions=True,
    )
    assert isinstance(results[0], DuplicateError)
    assert not any(isinstance(r, AssertionError) for r in results[1:]), results
    assert results[3] is True
    assert await db.get_tutor_by_telegram_id(99) is not None
    assert {g.name for g in await db.list_groups(tutor.id)} == {"Renamed", "Old", "Fresh"}

    # the same for a student registration racing a duplicate group name
    kwargs = student_kwargs(500, tutor.id, group.id)
    results = await asyncio.gather(
        db.add_group(tutor.id, "Old"),
        db.upsert_student(**kwargs),
        return_exceptions=True,
    )
    assert isinstance(results[0], DuplicateError)
    assert not isinstance(results[1], BaseException), results[1]
    assert await db.get_student_by_telegram_id(500) is not None


async def test_concurrent_upserts_report_exactly_one_new_registration(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    kwargs = student_kwargs(100, tutor.id, group.id)

    (first, first_is_update), (second, second_is_update) = await asyncio.gather(
        db.upsert_student(**kwargs), db.upsert_student(**kwargs)
    )
    assert sorted([first_is_update, second_is_update]) == [False, True]
    assert first.id == second.id
    assert len(await db.list_students()) == 1


async def test_get_and_delete_student(db: Database) -> None:
    tutor = await db.add_tutor("Karimov Aziz", 1)
    group = await db.add_group(tutor.id, "DI-21")
    saved, _ = await db.upsert_student(**student_kwargs(100, tutor.id, group.id, full_name="Zokirov Vali"))
    await db.upsert_student(**student_kwargs(101, tutor.id, group.id, full_name="Aliyev Olim"))

    by_id = await db.get_student(saved.id)
    assert by_id is not None and by_id.telegram_id == 100 and by_id.full_name == "Zokirov Vali"
    assert by_id.tutor_name == "Karimov Aziz" and by_id.group_name == "DI-21"
    assert await db.get_student(saved.id + 1000) is None

    other = await db.add_tutor("Boshqa Tyutor", 2)
    assert await db.delete_student(saved.id, tutor_id=other.id) is False  # not that tutor's student
    assert await db.get_student(saved.id) is not None
    assert await db.delete_student(saved.id, tutor_id=tutor.id) is True
    assert await db.delete_student(saved.id) is False  # the second tap finds nothing
    assert await db.get_student(saved.id) is None
    assert await db.get_student_by_telegram_id(100) is None
    assert [s.full_name for s in await db.list_students(group_id=group.id)] == ["Aliyev Olim"]
    refreshed = await db.get_group(group.id)
    assert refreshed is not None and refreshed.student_count == 1

    # a deleted student can register again from scratch and gets a fresh row
    again, is_update = await db.upsert_student(**student_kwargs(100, tutor.id, group.id))
    assert not is_update and again.id != saved.id


async def test_upsert_student_validates_residence_and_group(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    other = await db.add_tutor("O", 2)
    group = await db.add_group(tutor.id, "G")
    with pytest.raises(ValueError):
        await db.upsert_student(**student_kwargs(1, tutor.id, group.id, residence="hostel"))
    with pytest.raises(ValueError):
        await db.upsert_student(**student_kwargs(1, other.id, group.id))
    with pytest.raises(ValueError):
        await db.upsert_student(**student_kwargs(1, tutor.id, 999))


async def test_cascade_delete(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    keep = await db.add_tutor("K", 2)
    g1 = await db.add_group(tutor.id, "G1")
    g2 = await db.add_group(tutor.id, "G2")
    kg = await db.add_group(keep.id, "KG")
    for tg_id, group in ((1, g1), (2, g1), (3, g2)):
        await db.upsert_student(**student_kwargs(tg_id, tutor.id, group.id))
    await db.upsert_student(**student_kwargs(4, keep.id, kg.id))
    assert await db.count_tutor_groups_and_students(tutor.id) == (2, 3)

    assert await db.delete_group(g1.id) is True
    assert await db.count_tutor_groups_and_students(tutor.id) == (1, 1)
    assert await db.get_student_by_telegram_id(1) is None

    assert await db.delete_tutor(tutor.id) is True
    assert await db.count_tutor_groups_and_students(tutor.id) == (0, 0)
    assert await db.get_group(g2.id) is None
    assert await db.get_student_by_telegram_id(3) is None
    # unrelated tutor untouched
    assert await db.count_tutor_groups_and_students(keep.id) == (1, 1)
    assert len(await db.list_students()) == 1


async def test_list_students_filters_and_order(db: Database) -> None:
    t1 = await db.add_tutor("T1", 1)
    t2 = await db.add_tutor("T2", 2)
    b = await db.add_group(t1.id, "B-guruh")
    a = await db.add_group(t1.id, "A-guruh")
    other = await db.add_group(t2.id, "Z-guruh")

    await db.upsert_student(**student_kwargs(1, t1.id, b.id, full_name="Zokirov Z", residence="ttj"))
    await db.upsert_student(**student_kwargs(2, t1.id, b.id, full_name="Aliyev A", residence="kvartira"))
    await db.upsert_student(**student_kwargs(3, t1.id, a.id, full_name="Karimov K", residence="ttj"))
    await db.upsert_student(**student_kwargs(4, t2.id, other.id, full_name="Boshqa B", residence="ttj"))

    everyone = await db.list_students()
    assert [s.full_name for s in everyone] == ["Karimov K", "Aliyev A", "Zokirov Z", "Boshqa B"]
    assert all(s.tutor_name and s.group_name for s in everyone)

    by_tutor = await db.list_students(tutor_id=t1.id)
    assert [s.full_name for s in by_tutor] == ["Karimov K", "Aliyev A", "Zokirov Z"]

    by_group = await db.list_students(tutor_id=t1.id, group_id=b.id)
    assert [s.full_name for s in by_group] == ["Aliyev A", "Zokirov Z"]

    by_residence = await db.list_students(tutor_id=t1.id, residence="ttj")
    assert [(s.full_name, s.group_name) for s in by_residence] == [("Karimov K", "A-guruh"), ("Zokirov Z", "B-guruh")]

    assert await db.list_students(tutor_id=t1.id, residence="uy") == []
    assert [s.full_name for s in await db.list_students(residence="ttj")] == ["Karimov K", "Zokirov Z", "Boshqa B"]


async def test_init_is_idempotent_and_creates_parent_dir(tmp_path: Any) -> None:
    database = Database(tmp_path / "nested" / "dir" / "bot.db")
    await database.init()
    await database.init()
    assert (tmp_path / "nested" / "dir" / "bot.db").exists()
    await database.close()
    with pytest.raises(RuntimeError):
        _ = database.conn


# --------------------------------------------------- editing a saved student


async def test_update_student_writes_only_the_given_fields(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    student, _ = await db.upsert_student(**student_kwargs(100, tutor.id, group.id))

    edited = await db.update_student(100, phone="+998905555555", full_name="Yangi Ism")
    assert edited is not None
    assert edited.phone == "+998905555555" and edited.full_name == "Yangi Ism"
    assert edited.direction == student.direction  # untouched columns survive
    assert edited.id == student.id and edited.created_at == student.created_at
    assert edited.updated_at >= student.updated_at
    assert await db.get_student_by_telegram_id(100) == edited
    assert len(await db.list_students()) == 1


async def test_update_student_moves_the_row_to_another_tutor_and_group(db: Database) -> None:
    first = await db.add_tutor("T1", 1)
    second = await db.add_tutor("T2", 2)
    g1 = await db.add_group(first.id, "G1")
    g2 = await db.add_group(second.id, "G2")
    await db.upsert_student(**student_kwargs(100, first.id, g1.id))

    edited = await db.update_student(100, tutor_id=second.id, group_id=g2.id)
    assert edited is not None
    assert edited.tutor_id == second.id and edited.tutor_name == "T2"
    assert edited.group_id == g2.id and edited.group_name == "G2"
    assert await db.count_group_students(g1.id) == 0
    assert await db.count_group_students(g2.id) == 1
    assert await db.count_tutor_groups_and_students(first.id) == (1, 0)


async def test_update_student_rejects_bad_input_and_missing_rows(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    await db.upsert_student(**student_kwargs(100, tutor.id, group.id))

    assert await db.update_student(999, phone="+998905555555") is None  # nobody registered under 999
    with pytest.raises(ValueError):
        await db.update_student(100)
    for immutable in ("created_at", "updated_at", "telegram_id", "id", "nope"):
        with pytest.raises(ValueError, match="editable"):
            await db.update_student(100, **{immutable: "x"})
    with pytest.raises(ValueError, match="residence"):
        await db.update_student(100, residence="qasr")
    unchanged = await db.get_student_by_telegram_id(100)
    assert unchanged is not None and unchanged.phone == "+998901234567"


# ------------------------------------------------------------------- users


async def test_users_are_recorded_refreshed_and_paged(db: Database) -> None:
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    await db.touch_user(300, "vali", "Vali Aliyev")
    await db.touch_user(301, None, "Nomsiz Kishi")
    assert await db.count_users() == (2, 0)

    await db.upsert_student(**student_kwargs(300, tutor.id, group.id))
    assert await db.count_users() == (2, 1)

    users = await db.list_users(10)
    assert [u.telegram_id for u in users] == [300, 301]  # oldest first
    assert (users[0].is_student, users[1].is_student) == (True, False)
    assert users[0].username == "vali" and users[1].username is None

    # a second /start refreshes the profile instead of inserting a duplicate
    await db.touch_user(300, "vali_new", "Vali Aliyev Yangi")
    assert await db.count_users() == (2, 1)
    again = await db.list_users(10)
    assert again[0].username == "vali_new" and again[0].full_name == "Vali Aliyev Yangi"
    assert again[0].started_at == users[0].started_at

    assert [u.telegram_id for u in await db.list_users(1)] == [300]
    assert [u.telegram_id for u in await db.list_users(1, 1)] == [301]
    assert await db.list_users(10, 5) == []


async def test_students_saved_before_the_users_table_are_backfilled(tmp_path: Path) -> None:
    """A database written before /users existed still lists everyone who had registered."""
    first = Database(tmp_path / "backfill.db")
    await first.init()
    tutor = await first.add_tutor("T", 1)
    group = await first.add_group(tutor.id, "G")
    await first.upsert_student(**student_kwargs(100, tutor.id, group.id))
    await first.conn.execute("DELETE FROM users")  # as if the table had just been added
    await first.conn.commit()
    assert await first.count_users() == (0, 0)
    await first.close()

    reopened = Database(tmp_path / "backfill.db")
    await reopened.init()
    assert await reopened.count_users() == (1, 1)
    listed = await reopened.list_users(10)
    assert [u.telegram_id for u in listed] == [100]
    assert listed[0].is_student and listed[0].username == "user100"
    await reopened.close()


async def test_older_database_gains_the_edited_at_column(tmp_path: Path) -> None:
    """A database written before ``edited_at`` existed is migrated on the next start."""
    path = tmp_path / "old.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE students (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telegram_id INTEGER NOT NULL UNIQUE,
          username TEXT,
          tutor_id INTEGER NOT NULL,
          group_id INTEGER NOT NULL,
          full_name TEXT NOT NULL,
          phone TEXT NOT NULL,
          direction TEXT NOT NULL,
          residence TEXT NOT NULL,
          address TEXT NOT NULL,
          father_name TEXT NOT NULL,
          father_phone TEXT NOT NULL,
          mother_name TEXT NOT NULL,
          mother_phone TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        """
    )
    legacy.close()

    db = Database(path)
    await db.init()
    tutor = await db.add_tutor("T", 1)
    group = await db.add_group(tutor.id, "G")
    await db.upsert_student(**student_kwargs(100, tutor.id, group.id))
    fresh = await db.get_student_by_telegram_id(100)
    assert fresh is not None and fresh.edited_at is None

    edited = await db.update_student(100, phone="+998905555555")
    assert edited is not None and edited.edited_at
    await db.close()


async def test_older_database_accepts_a_residence_added_later(tmp_path: Path) -> None:
    """A table whose CHECK predates ``qarindosh`` is rebuilt: rows, ids and the id counter survive."""
    path = tmp_path / "old.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE tutors (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          telegram_id INTEGER NOT NULL UNIQUE,
          created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE groups (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tutor_id INTEGER NOT NULL REFERENCES tutors(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
          UNIQUE(tutor_id, name)
        );
        CREATE TABLE students (
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
          updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
          edited_at TEXT
        );
        INSERT INTO tutors (name, telegram_id) VALUES ('Karimov Aziz', 1);
        INSERT INTO groups (tutor_id, name) VALUES (1, 'DI-21');
        INSERT INTO students (telegram_id, username, tutor_id, group_id, full_name, phone, direction,
                              residence, address, father_name, father_phone, mother_name, mother_phone)
        VALUES (100, 'vali', 1, 1, 'Zokirov Vali', '+998901234567', 'Dasturiy injiniring',
                'uy', 'Toshkent, Chilonzor 5', 'Ota', '+998901111111', 'Ona', '+998902222222'),
               (101, NULL, 1, 1, 'Ketgan Talaba', '+998900000000', 'X',
                'ttj', 'TTJ', 'Ota', '+998901111111', 'Ona', '+998902222222');
        DELETE FROM students WHERE telegram_id = 101;
        """
    )
    legacy.commit()
    legacy.close()

    db = Database(path)
    await db.init()
    kept = await db.get_student_by_telegram_id(100)
    assert kept is not None
    assert kept.id == 1 and kept.full_name == "Zokirov Vali" and kept.residence == "uy"
    assert kept.address == "Toshkent, Chilonzor 5" and kept.tutor_name == "Karimov Aziz" and kept.edited_at is None

    saved, is_update = await db.upsert_student(
        **student_kwargs(102, 1, 1, residence="qarindosh", address="Samarqand, Registon 3")
    )
    assert not is_update and saved.residence == "qarindosh" and saved.address == "Samarqand, Registon 3"
    assert saved.id == 3  # the deleted student's id is not handed out again
    assert [s.residence for s in await db.list_students(residence="qarindosh")] == ["qarindosh"]

    # the constraint is still there, only wider; the foreign keys still cascade
    with pytest.raises(sqlite3.IntegrityError):
        await db.conn.execute("UPDATE students SET residence = 'hotel' WHERE id = 1")
    await db.conn.rollback()
    assert await db.delete_tutor(1)
    assert await db.list_students() == []
    await db.close()

    # a second start finds the table up to date and leaves it alone
    again = Database(path)
    await again.init()
    assert await again.list_students() == []
    await again.close()


async def test_test_user_list_prefers_the_live_profile_name(db: Database) -> None:
    """The stored label is only a fallback for someone who has never pressed /start."""
    assert await db.add_test_user(500, "Forward orqali olingan ism") is True
    assert await db.add_test_user(500) is False  # already on the list
    assert await db.add_test_user(501) is True
    assert await db.is_test_user(500) and not await db.is_test_user(502)

    listed = {u.telegram_id: u for u in await db.list_test_users()}
    assert listed[500].name == "Forward orqali olingan ism" and listed[500].username is None
    assert listed[501].name == ""

    await db.touch_user(500, "tester", "Test Foydalanuvchi")
    refreshed = {u.telegram_id: u for u in await db.list_test_users()}
    assert refreshed[500].name == "Test Foydalanuvchi" and refreshed[500].username == "tester"

    assert await db.remove_test_user(500) is True
    assert await db.remove_test_user(500) is False
    assert [u.telegram_id for u in await db.list_test_users()] == [501]
