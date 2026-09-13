"""Database layer: tutor/group CRUD, uniqueness, cascades, student upsert and list filters."""

from __future__ import annotations

import asyncio
import sqlite3
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
