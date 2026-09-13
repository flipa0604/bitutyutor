"""Plain dataclasses mirroring database rows."""

from __future__ import annotations

from dataclasses import dataclass

RESIDENCE_VALUES: tuple[str, ...] = ("ttj", "kvartira", "uy")


@dataclass(frozen=True, slots=True)
class Tutor:
    id: int
    name: str
    telegram_id: int
    created_at: str


@dataclass(frozen=True, slots=True)
class BotUser:
    """Someone who has pressed /start, whether or not they finished registering."""

    telegram_id: int
    username: str | None
    full_name: str
    started_at: str
    last_start_at: str
    is_student: bool = False


@dataclass(frozen=True, slots=True)
class TestUser:
    """A Telegram ID allowed to run the registration flow again after it already has a row.

    ``name`` and ``username`` are looked up from the ``users`` table when that person has ever
    pressed /start, so the admin list stays readable without asking for a label.
    """

    telegram_id: int
    name: str
    created_at: str
    username: str | None = None


@dataclass(frozen=True, slots=True)
class Group:
    id: int
    tutor_id: int
    name: str
    created_at: str
    student_count: int = 0


@dataclass(frozen=True, slots=True)
class Student:
    id: int
    telegram_id: int
    username: str | None
    tutor_id: int
    group_id: int
    full_name: str
    phone: str
    direction: str
    residence: str
    address: str
    father_name: str
    father_phone: str
    mother_name: str
    mother_phone: str
    created_at: str
    updated_at: str
    edited_at: str | None = None
    """When the data was last changed after registration; ``None`` while it never was."""
    tutor_name: str = ""
    group_name: str = ""
